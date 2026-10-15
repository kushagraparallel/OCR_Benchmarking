"""Optional docTR adapter using an explicitly configured, reusable predictor."""

import importlib
import importlib.metadata
import io
import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRAdapterError, OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRBoundingBox, OCRImage, OCRResult, OCRWord

logger = logging.getLogger(__name__)

DEFAULT_MAX_IMAGE_PIXELS = 40_000_000


class DocTRAdapter(OCRAdapter):
    """Recognize text with docTR using a caller-configured predictor factory.

    A factory is required so applications can load vetted local model weights and
    choose architectures explicitly. The adapter never downloads pretrained weights
    implicitly. The resulting predictor is initialized once and reused.
    """

    def __init__(
        self,
        predictor_factory: Callable[[], Any],
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> None:
        if not callable(predictor_factory):
            raise ValueError("predictor_factory must be callable.")
        if max_image_pixels < 1:
            raise ValueError("max_image_pixels must be a positive integer.")

        self._predictor_factory = predictor_factory
        self._max_image_pixels = max_image_pixels
        self._predictor: Any | None = None
        self._predictor_lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        """Return the stable engine name used in benchmark records."""
        return "doctr"

    def get_version(self) -> str:
        """Return the installed python-doctr package version without loading models."""
        try:
            return importlib.metadata.version("python-doctr")
        except importlib.metadata.PackageNotFoundError as exc:
            raise OCRDependencyError(
                "docTR is not installed. Install the optional OCR dependencies."
            ) from exc
        except Exception as exc:
            logger.exception("Could not determine the docTR version")
            raise OCRDependencyError("The docTR installation could not be inspected.") from exc

    def recognize(self, image: OCRImage) -> OCRResult:
        """Recognize one image and normalize docTR's nested document output."""
        self._validate_image(image.image_bytes)
        engine_version = self.get_version()
        predictor = self._get_predictor()

        try:
            doctr_io = importlib.import_module("doctr.io")
            document = doctr_io.DocumentFile.from_images([image.image_bytes])
            start_time = time.perf_counter()
            with self._predictor_lock:
                prediction = predictor(document)
            duration_ms = (time.perf_counter() - start_time) * 1000
            exported_result = prediction.export()
        except OCRAdapterError:
            raise
        except Exception as exc:
            logger.exception("docTR failed while recognizing page %s", image.page_number)
            raise OCRExecutionError("docTR failed to process the image.") from exc

        words = self._normalize_export(exported_result)
        return OCRResult(
            engine_name=self.engine_name,
            engine_version=engine_version,
            page_number=image.page_number,
            text=self._build_text(words),
            words=words,
            duration_ms=round(duration_ms, 3),
        )

    def _get_predictor(self) -> Any:
        """Create the configured predictor once, protecting concurrent initialization."""
        if self._predictor is not None:
            return self._predictor

        with self._predictor_lock:
            if self._predictor is not None:
                return self._predictor
            try:
                importlib.import_module("doctr")
                self._predictor = self._predictor_factory()
            except ModuleNotFoundError as exc:
                raise OCRDependencyError(
                    "docTR dependencies are unavailable. Install the optional OCR dependencies."
                ) from exc
            except Exception as exc:
                logger.exception("docTR predictor initialization failed")
                raise OCRDependencyError(
                    "docTR could not initialize. Verify local model weights and runtime settings."
                ) from exc
        return self._predictor

    def _validate_image(self, image_bytes: bytes) -> None:
        """Decode the image and enforce a pixel limit before invoking model inference."""
        if not image_bytes:
            raise OCRInputError("The supplied image is empty.")
        try:
            with Image.open(io.BytesIO(image_bytes)) as source_image:
                source_image.load()
                if source_image.width * source_image.height > self._max_image_pixels:
                    raise OCRInputError(
                        f"The image exceeds the {self._max_image_pixels}-pixel processing limit."
                    )
        except OCRInputError:
            raise
        except Image.DecompressionBombError as exc:
            raise OCRInputError("The image exceeds Pillow's safe decoding limits.") from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise OCRInputError("The supplied bytes are not a readable image.") from exc

    @staticmethod
    def _normalize_export(exported_result: Any) -> tuple[OCRWord, ...]:
        """Convert docTR exported page/block/line/word data into pixel-space words."""
        if not isinstance(exported_result, dict):
            raise OCRExecutionError("docTR returned malformed document data.")
        pages = exported_result.get("pages")
        if not isinstance(pages, list):
            raise OCRExecutionError("docTR returned malformed document data.")
        if not pages:
            return ()

        page = pages[0]
        if not isinstance(page, dict):
            raise OCRExecutionError("docTR returned malformed page data.")
        dimensions = page.get("dimensions")
        if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 2:
            raise OCRExecutionError("docTR returned invalid page dimensions.")
        try:
            page_height, page_width = int(dimensions[0]), int(dimensions[1])
        except (TypeError, ValueError) as exc:
            raise OCRExecutionError("docTR returned invalid page dimensions.") from exc
        if page_width < 1 or page_height < 1:
            raise OCRExecutionError("docTR returned invalid page dimensions.")

        blocks = page.get("blocks", [])
        if not isinstance(blocks, list):
            raise OCRExecutionError("docTR returned malformed block data.")

        words: list[OCRWord] = []
        for block in blocks:
            for line in block.get("lines", []):
                for word in line.get("words", []):
                    try:
                        text = str(word["value"]).strip()
                        geometry = word["geometry"]
                        (left, top), (right, bottom) = geometry
                        left, top, right, bottom = (
                            float(left), float(top), float(right), float(bottom)
                        )
                        confidence_value = float(word.get("confidence", float("nan")))
                        if not all(
                            math.isfinite(value)
                            for value in (left, top, right, bottom)
                        ):
                            raise ValueError("Non-finite geometry.")
                        if right < left or bottom < top:
                            raise ValueError("Invalid geometry.")
                    except (KeyError, TypeError, ValueError, IndexError) as exc:
                        raise OCRExecutionError("docTR returned malformed word data.") from exc

                    if not text:
                        continue
                    left_pixel = math.floor(left * page_width)
                    top_pixel = math.floor(top * page_height)
                    right_pixel = math.ceil(right * page_width)
                    bottom_pixel = math.ceil(bottom * page_height)
                    confidence = (
                        confidence_value * 100.0
                        if math.isfinite(confidence_value)
                        and 0.0 <= confidence_value <= 1.0
                        else None
                    )
                    words.append(
                        OCRWord(
                            text=text,
                            bounding_box=OCRBoundingBox(
                                x=max(0, left_pixel),
                                y=max(0, top_pixel),
                                width=max(0, right_pixel - left_pixel),
                                height=max(0, bottom_pixel - top_pixel),
                            ),
                            confidence=confidence,
                        )
                    )
        return tuple(words)

    @staticmethod
    def _build_text(words: tuple[OCRWord, ...]) -> str:
        """Join recognized words in docTR's exported reading order."""
        return " ".join(word.text for word in words)
