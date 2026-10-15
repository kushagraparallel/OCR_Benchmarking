"""Optional PaddleOCR adapter with pre-provisioned models and normalized output."""

import importlib
import importlib.metadata
import io
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRAdapterError, OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRBoundingBox, OCRImage, OCRResult, OCRWord

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000
# PaddleOCR's own default (960) silently downscales the longer side of every
# input before detection. Rendered PDF pages routinely exceed that (e.g. a
# standard page at 200 DPI is ~2300px tall), which shrinks small body text
# below a detectable size and yields an empty, silently "successful" result.
# This default instead matches PDFPageRenderer's configured ceiling
# (max_page_dimension_pixels=10_000 in the worker), so PaddleOCR never
# re-downscales an image our own pipeline already decided was acceptable.
DEFAULT_DETECTION_IMAGE_SIDE_LIMIT = 10_000


class PaddleOCRAdapter(OCRAdapter):
    """Recognize text with PaddleOCR while reusing one initialized model instance.

    PaddleOCR and its native runtime are imported lazily. Explicit model directories
    are required to prevent model downloads from being triggered by API requests.
    """

    def __init__(
        self,
        detection_model_directory: str | Path,
        recognition_model_directory: str | Path,
        classification_model_directory: str | Path | None = None,
        language: str = DEFAULT_LANGUAGE,
        use_angle_classification: bool = True,
        use_gpu: bool = False,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
        detection_image_side_limit: int = DEFAULT_DETECTION_IMAGE_SIDE_LIMIT,
    ) -> None:
        if not language.strip():
            raise ValueError("language must not be empty.")
        if max_image_pixels < 1:
            raise ValueError("max_image_pixels must be a positive integer.")
        if detection_image_side_limit < 1:
            raise ValueError("detection_image_side_limit must be a positive integer.")
        if use_angle_classification and classification_model_directory is None:
            raise ValueError(
                "classification_model_directory is required when angle classification is enabled."
            )

        self._detection_model_directory = self._validate_model_directory(
            detection_model_directory, "detection_model_directory"
        )
        self._recognition_model_directory = self._validate_model_directory(
            recognition_model_directory, "recognition_model_directory"
        )
        self._classification_model_directory = (
            self._validate_model_directory(
                classification_model_directory, "classification_model_directory"
            )
            if classification_model_directory is not None
            else None
        )
        self._language = language.strip()
        self._use_angle_classification = use_angle_classification
        self._use_gpu = use_gpu
        self._max_image_pixels = max_image_pixels
        self._detection_image_side_limit = detection_image_side_limit
        self._engine: Any | None = None
        self._engine_lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        """Return the stable engine name used in benchmark records."""
        return "paddleocr"

    def get_version(self) -> str:
        """Return the installed PaddleOCR package version without loading its models."""
        try:
            return importlib.metadata.version("paddleocr")
        except importlib.metadata.PackageNotFoundError as exc:
            raise OCRDependencyError(
                "PaddleOCR is not installed. Install the optional OCR dependencies."
            ) from exc
        except Exception as exc:
            logger.exception("Could not determine the PaddleOCR version")
            raise OCRDependencyError("The PaddleOCR installation could not be inspected.") from exc

    def recognize(self, image: OCRImage) -> OCRResult:
        """Recognize one encoded image and normalize text, bounds, confidence, and timing."""
        decoded_image = self._decode_image(image.image_bytes)
        engine_version = self.get_version()
        engine = self._get_engine()

        try:
            numpy = importlib.import_module("numpy")
            image_array = numpy.asarray(decoded_image)
            start_time = time.perf_counter()
            with self._engine_lock:
                raw_result = engine.ocr(
                    image_array,
                    cls=self._use_angle_classification,
                )
            duration_ms = (time.perf_counter() - start_time) * 1000
        except OCRAdapterError:
            raise
        except Exception as exc:
            logger.exception("PaddleOCR failed while recognizing page %s", image.page_number)
            raise OCRExecutionError("PaddleOCR failed to process the image.") from exc

        words = self._normalize_detections(raw_result)
        return OCRResult(
            engine_name=self.engine_name,
            engine_version=engine_version,
            page_number=image.page_number,
            text=self._build_text(words),
            words=words,
            duration_ms=round(duration_ms, 3),
        )

    def _get_engine(self) -> Any:
        """Initialize the PaddleOCR runtime once and reuse it across pages."""
        if self._engine is not None:
            return self._engine

        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            try:
                paddleocr = importlib.import_module("paddleocr")
                self._engine = paddleocr.PaddleOCR(
                    lang=self._language,
                    use_angle_cls=self._use_angle_classification,
                    use_gpu=self._use_gpu,
                    det_model_dir=str(self._detection_model_directory),
                    rec_model_dir=str(self._recognition_model_directory),
                    cls_model_dir=(
                        str(self._classification_model_directory)
                        if self._classification_model_directory is not None
                        else None
                    ),
                    det_limit_side_len=self._detection_image_side_limit,
                    show_log=False,
                )
            except ModuleNotFoundError as exc:
                raise OCRDependencyError(
                    "PaddleOCR dependencies are unavailable. Install the optional OCR dependencies."
                ) from exc
            except Exception as exc:
                logger.exception("PaddleOCR model initialization failed")
                raise OCRDependencyError(
                    "PaddleOCR could not initialize. Verify model files and runtime settings."
                ) from exc
        return self._engine

    @staticmethod
    def _validate_model_directory(directory: str | Path, setting_name: str) -> Path:
        """Require existing local model directories so requests never fetch model files."""
        model_directory = Path(directory).expanduser()
        if not model_directory.is_dir():
            raise ValueError(f"{setting_name} must point to an existing directory.")
        return model_directory.resolve()

    def _decode_image(self, image_bytes: bytes) -> Image.Image:
        """Decode image bytes and enforce the maximum decoded pixel count."""
        if not image_bytes:
            raise OCRInputError("The supplied image is empty.")
        try:
            with Image.open(io.BytesIO(image_bytes)) as source_image:
                source_image.load()
                if source_image.width * source_image.height > self._max_image_pixels:
                    raise OCRInputError(
                        f"The image exceeds the {self._max_image_pixels}-pixel processing limit."
                    )
                return source_image.convert("RGB")
        except OCRInputError:
            raise
        except Image.DecompressionBombError as exc:
            raise OCRInputError("The image exceeds Pillow's safe decoding limits.") from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise OCRInputError("The supplied bytes are not a readable image.") from exc

    @staticmethod
    def _normalize_detections(raw_result: Any) -> tuple[OCRWord, ...]:
        """Convert PaddleOCR's nested polygon/text detections to normalized words."""
        if raw_result is None:
            return ()

        detections: Any = raw_result
        if (
            isinstance(detections, (list, tuple))
            and len(detections) == 1
            and (detections[0] is None or isinstance(detections[0], (list, tuple)))
        ):
            detections = detections[0]
        if detections is None:
            return ()
        if not isinstance(detections, (list, tuple)):
            raise OCRExecutionError("PaddleOCR returned malformed detection data.")

        words: list[OCRWord] = []
        for detection in detections:
            if detection is None:
                continue
            try:
                polygon, recognition = detection
                raw_text, raw_confidence = recognition
                text = str(raw_text).strip()
                if not text:
                    continue
                points = [(float(point[0]), float(point[1])) for point in polygon]
                if not points:
                    raise ValueError("The polygon is empty.")
                left = min(point[0] for point in points)
                top = min(point[1] for point in points)
                right = max(point[0] for point in points)
                bottom = max(point[1] for point in points)
                confidence_value = float(raw_confidence)
                if not all(math.isfinite(value) for value in (left, top, right, bottom)):
                    raise ValueError("The polygon contains non-finite coordinates.")
            except (TypeError, ValueError, IndexError, KeyError) as exc:
                raise OCRExecutionError("PaddleOCR returned malformed detection data.") from exc

            if right < left or bottom < top:
                raise OCRExecutionError("PaddleOCR returned invalid word coordinates.")
            confidence = (
                confidence_value * 100.0
                if math.isfinite(confidence_value) and 0.0 <= confidence_value <= 1.0
                else None
            )
            left_pixel = math.floor(left)
            top_pixel = math.floor(top)
            words.append(
                OCRWord(
                    text=text,
                    bounding_box=OCRBoundingBox(
                        x=max(0, left_pixel),
                        y=max(0, top_pixel),
                        width=max(0, math.ceil(right) - left_pixel),
                        height=max(0, math.ceil(bottom) - top_pixel),
                    ),
                    confidence=confidence,
                )
            )
        return tuple(words)

    @staticmethod
    def _build_text(words: tuple[OCRWord, ...]) -> str:
        """Join detected text in the reading order returned by PaddleOCR."""
        return "\n".join(word.text for word in words)
