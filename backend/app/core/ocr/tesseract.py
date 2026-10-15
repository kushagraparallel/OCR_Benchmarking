"""Tesseract OCR adapter with normalized word output and bounded execution time."""

import io
import logging
import time
from collections import OrderedDict
from pathlib import Path

from PIL import Image, UnidentifiedImageError
import pytesseract
from pytesseract import Output
from pytesseract.pytesseract import (
    TesseractError,
    TesseractNotFoundError,
    TesseractTimeoutError,
)

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRBoundingBox, OCRImage, OCRResult, OCRWord

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "eng"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000
DEFAULT_TESSERACT_CONFIG = "--oem 3 --psm 3"


class TesseractOCRAdapter(OCRAdapter):
    """Run Tesseract against encoded page images and normalize its output."""

    def __init__(
        self,
        language: str = DEFAULT_LANGUAGE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
        tesseract_cmd: str | Path | None = None,
        config: str = DEFAULT_TESSERACT_CONFIG,
    ) -> None:
        if not language.strip():
            raise ValueError("language must not be empty.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if max_image_pixels < 1:
            raise ValueError("max_image_pixels must be a positive integer.")

        self._language = language.strip()
        self._timeout_seconds = timeout_seconds
        self._max_image_pixels = max_image_pixels
        self._config = config
        if tesseract_cmd is not None:
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)

    @property
    def engine_name(self) -> str:
        """Return the stable engine name used in benchmark records."""
        return "tesseract"

    def get_version(self) -> str:
        """Return the native Tesseract version, failing clearly if unavailable."""
        try:
            return str(pytesseract.get_tesseract_version())
        except (TesseractNotFoundError, OSError) as exc:
            raise OCRDependencyError(
                "Tesseract is not installed or its executable is not on PATH."
            ) from exc
        except Exception as exc:
            logger.exception("Could not determine the Tesseract version")
            raise OCRDependencyError("The Tesseract runtime could not be inspected.") from exc

    def recognize(self, image: OCRImage) -> OCRResult:
        """Recognize text from one encoded image and return normalized word data."""
        decoded_image = self._decode_image(image.image_bytes)
        engine_version = self.get_version()
        start_time = time.perf_counter()

        try:
            image_data = pytesseract.image_to_data(
                decoded_image,
                lang=self._language,
                config=self._config,
                output_type=Output.DICT,
                timeout=self._timeout_seconds,
            )
        except TesseractTimeoutError as exc:
            raise OCRExecutionError(
                f"Tesseract exceeded the {self._timeout_seconds:g}-second timeout."
            ) from exc
        except TesseractNotFoundError as exc:
            raise OCRDependencyError(
                "Tesseract is not installed or its executable is not on PATH."
            ) from exc
        except TesseractError as exc:
            raise OCRExecutionError(
                "Tesseract could not recognize the supplied image. Check the language data."
            ) from exc
        except (OSError, RuntimeError) as exc:
            logger.exception("Tesseract failed while recognizing page %s", image.page_number)
            raise OCRExecutionError("Tesseract failed to process the image.") from exc

        duration_ms = (time.perf_counter() - start_time) * 1000
        words = self._normalize_words(image_data)
        text = self._build_text(image_data)
        return OCRResult(
            engine_name=self.engine_name,
            engine_version=engine_version,
            page_number=image.page_number,
            text=text,
            words=words,
            duration_ms=round(duration_ms, 3),
        )

    def _decode_image(self, image_bytes: bytes) -> Image.Image:
        """Decode image bytes and reject invalid or excessively large images."""
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
    def _normalize_words(image_data: dict[str, list[object]]) -> tuple[OCRWord, ...]:
        """Convert Tesseract's word-level dictionary to stable typed records."""
        normalized_words: list[OCRWord] = []
        text_values = image_data.get("text", [])

        for index, raw_text in enumerate(text_values):
            word_text = str(raw_text).strip()
            if not word_text:
                continue

            try:
                x = int(image_data["left"][index])
                y = int(image_data["top"][index])
                width = int(image_data["width"][index])
                height = int(image_data["height"][index])
                raw_confidence = float(image_data["conf"][index])
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise OCRExecutionError("Tesseract returned malformed word coordinates.") from exc

            if width < 0 or height < 0:
                raise OCRExecutionError("Tesseract returned invalid word coordinates.")
            confidence = raw_confidence if 0.0 <= raw_confidence <= 100.0 else None
            normalized_words.append(
                OCRWord(
                    text=word_text,
                    bounding_box=OCRBoundingBox(x=x, y=y, width=width, height=height),
                    confidence=confidence,
                )
            )

        return tuple(normalized_words)

    @staticmethod
    def _build_text(image_data: dict[str, list[object]]) -> str:
        """Reconstruct line breaks from Tesseract's block, paragraph, and line IDs."""
        line_words: OrderedDict[tuple[int, int, int], list[str]] = OrderedDict()
        text_values = image_data.get("text", [])

        for index, raw_text in enumerate(text_values):
            word_text = str(raw_text).strip()
            if not word_text:
                continue
            try:
                line_key = (
                    int(image_data["block_num"][index]),
                    int(image_data["par_num"][index]),
                    int(image_data["line_num"][index]),
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise OCRExecutionError("Tesseract returned malformed line identifiers.") from exc
            line_words.setdefault(line_key, []).append(word_text)

        return "\n".join(" ".join(words) for words in line_words.values())
