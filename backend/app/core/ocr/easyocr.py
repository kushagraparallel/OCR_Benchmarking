"""Optional EasyOCR adapter with lazy model initialization and normalized output."""

import importlib
import importlib.metadata
import io
import logging
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRBoundingBox, OCRImage, OCRResult, OCRWord

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGES = ("en",)
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000


class EasyOCRAdapter(OCRAdapter):
    """Recognize text with EasyOCR while reusing its costly reader/model instance.

    EasyOCR and NumPy are imported only when recognition is first requested. Model
    initialization is lazy and model downloads are disabled by default to avoid
    unexpected network access in production requests.
    """

    def __init__(
        self,
        languages: tuple[str, ...] = DEFAULT_LANGUAGES,
        gpu: bool = False,
        model_storage_directory: str | Path | None = None,
        download_enabled: bool = False,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> None:
        normalized_languages = tuple(language.strip() for language in languages if language.strip())
        if not normalized_languages:
            raise ValueError("languages must contain at least one non-empty language code.")
        if max_image_pixels < 1:
            raise ValueError("max_image_pixels must be a positive integer.")

        self._languages = normalized_languages
        self._gpu = gpu
        self._model_storage_directory = (
            str(model_storage_directory) if model_storage_directory is not None else None
        )
        self._download_enabled = download_enabled
        self._max_image_pixels = max_image_pixels
        self._reader: Any | None = None
        self._reader_lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        """Return the stable engine name used in benchmark records."""
        return "easyocr"

    def get_version(self) -> str:
        """Return the installed EasyOCR package version without loading its models."""
        try:
            return importlib.metadata.version("easyocr")
        except importlib.metadata.PackageNotFoundError as exc:
            raise OCRDependencyError(
                "EasyOCR is not installed. Install the optional OCR dependencies."
            ) from exc
        except Exception as exc:
            logger.exception("Could not determine the EasyOCR version")
            raise OCRDependencyError("The EasyOCR installation could not be inspected.") from exc

    def recognize(self, image: OCRImage) -> OCRResult:
        """Recognize one encoded image and normalize words, bounds, confidence, and timing."""
        decoded_image = self._decode_image(image.image_bytes)
        engine_version = self.get_version()
        reader = self._get_reader()

        try:
            numpy = importlib.import_module("numpy")
            image_array = numpy.asarray(decoded_image)
            start_time = time.perf_counter()
            with self._reader_lock:
                detections = reader.readtext(image_array, detail=1, paragraph=False)
            duration_ms = (time.perf_counter() - start_time) * 1000
        except OCRAdapterErrorPassthrough:
            raise
        except Exception as exc:
            logger.exception("EasyOCR failed while recognizing page %s", image.page_number)
            raise OCRExecutionError("EasyOCR failed to process the image.") from exc

        words = self._normalize_detections(detections)
        text = self._build_text(words)
        return OCRResult(
            engine_name=self.engine_name,
            engine_version=engine_version,
            page_number=image.page_number,
            text=text,
            words=words,
            duration_ms=round(duration_ms, 3),
        )

    def _get_reader(self) -> Any:
        """Initialize the model once and reuse it for subsequent pages."""
        if self._reader is not None:
            return self._reader

        with self._reader_lock:
            if self._reader is not None:
                return self._reader
            try:
                easyocr = importlib.import_module("easyocr")
                self._reader = easyocr.Reader(
                    list(self._languages),
                    gpu=self._gpu,
                    model_storage_directory=self._model_storage_directory,
                    download_enabled=self._download_enabled,
                )
            except ModuleNotFoundError as exc:
                raise OCRDependencyError(
                    "EasyOCR dependencies are unavailable. Install the optional OCR dependencies."
                ) from exc
            except Exception as exc:
                logger.exception("EasyOCR model initialization failed")
                raise OCRDependencyError(
                    "EasyOCR could not initialize its model. Verify model files and runtime settings."
                ) from exc
        return self._reader

    def _decode_image(self, image_bytes: bytes) -> Image.Image:
        """Decode and bound image size before allocating an OCR model input."""
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
    def _normalize_detections(detections: list[Any]) -> tuple[OCRWord, ...]:
        """Convert EasyOCR polygon detections to pixel-aligned rectangular word bounds."""
        words: list[OCRWord] = []
        for detection in detections:
            try:
                polygon, raw_text, raw_confidence = detection
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
            except (TypeError, ValueError, IndexError, KeyError) as exc:
                raise OCRExecutionError("EasyOCR returned malformed detection data.") from exc

            if right < left or bottom < top:
                raise OCRExecutionError("EasyOCR returned invalid word coordinates.")
            confidence = (
                confidence_value
                if 0.0 <= confidence_value <= 1.0
                else None
            )
            words.append(
                OCRWord(
                    text=text,
                    bounding_box=OCRBoundingBox(
                        x=max(0, int(left)),
                        y=max(0, int(top)),
                        width=max(0, int(right - left)),
                        height=max(0, int(bottom - top)),
                    ),
                    confidence=confidence,
                )
            )
        return tuple(words)

    @staticmethod
    def _build_text(words: tuple[OCRWord, ...]) -> str:
        """Join detected text in the reading order returned by EasyOCR."""
        return "\n".join(word.text for word in words)


class OCRAdapterErrorPassthrough(Exception):
    """Internal marker retained only for explicit exception handling."""
