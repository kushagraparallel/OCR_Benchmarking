"""Unit tests for the normalized Tesseract OCR adapter."""

import io
from unittest.mock import patch

from PIL import Image
import pytest

from app.core.ocr.errors import OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRImage
from app.core.ocr.tesseract import TesseractOCRAdapter


def create_png_bytes(width: int = 120, height: int = 60) -> bytes:
    """Create a deterministic PNG image in memory."""
    with Image.new("RGB", (width, height), "white") as image:
        image_buffer = io.BytesIO()
        image.save(image_buffer, format="PNG")
        return image_buffer.getvalue()


def create_tesseract_data() -> dict[str, list[object]]:
    """Return representative Tesseract word-level output, including an empty token."""
    return {
        "level": [5, 5, 5],
        "page_num": [1, 1, 1],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 2],
        "word_num": [1, 2, 1],
        "left": [10, 50, 10],
        "top": [12, 12, 35],
        "width": [30, 20, 25],
        "height": [12, 12, 10],
        "conf": [95, -1, 80],
        "text": ["OCRLab", "", "ready"],
    }


def test_recognize_returns_normalized_words_and_text() -> None:
    """Successful recognition should normalize text, confidence, bounds, and timing."""
    adapter = TesseractOCRAdapter()
    with (
        patch.object(adapter, "get_version", return_value="5.4.1"),
        patch(
            "app.core.ocr.tesseract.pytesseract.image_to_data",
            return_value=create_tesseract_data(),
        ),
    ):
        result = adapter.recognize(OCRImage(create_png_bytes(), page_number=2))

    assert result.engine_name == "tesseract"
    assert result.engine_version == "5.4.1"
    assert result.page_number == 2
    assert result.text == "OCRLab\nready"
    assert len(result.words) == 2
    assert result.words[0].text == "OCRLab"
    assert result.words[0].bounding_box.x == 10
    assert result.words[0].confidence == 95.0
    assert result.words[1].confidence == 80.0
    assert result.duration_ms >= 0


def test_recognize_rejects_invalid_image_bytes() -> None:
    """Invalid image data should fail before invoking the native OCR runtime."""
    adapter = TesseractOCRAdapter()
    with pytest.raises(OCRInputError, match="not a readable image"):
        adapter.recognize(OCRImage(b"not-an-image", page_number=1))


def test_recognize_rejects_images_over_pixel_limit() -> None:
    """Image dimensions should be bounded before expensive OCR processing."""
    adapter = TesseractOCRAdapter(max_image_pixels=100)
    with pytest.raises(OCRInputError, match="processing limit"):
        adapter.recognize(OCRImage(create_png_bytes(20, 20), page_number=1))


def test_recognize_converts_engine_timeout_to_domain_error() -> None:
    """Tesseract timeouts should be reported consistently to benchmark orchestration."""
    adapter = TesseractOCRAdapter()
    with (
        patch.object(adapter, "get_version", return_value="5.4.1"),
        patch(
            "app.core.ocr.tesseract.pytesseract.image_to_data",
            side_effect=RuntimeError("Tesseract process timeout"),
        ),
        pytest.raises(OCRExecutionError, match="exceeded"),
    ):
        adapter.recognize(OCRImage(create_png_bytes(), page_number=1))


def test_ocr_image_requires_positive_page_number() -> None:
    """Page identity is one-based and validated at the common adapter boundary."""
    with pytest.raises(ValueError, match="positive"):
        OCRImage(create_png_bytes(), page_number=0)


def test_adapter_rejects_invalid_configuration() -> None:
    """Invalid timeout, pixel limits, and language should fail at construction."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        TesseractOCRAdapter(timeout_seconds=0)
    with pytest.raises(ValueError, match="max_image_pixels"):
        TesseractOCRAdapter(max_image_pixels=0)
    with pytest.raises(ValueError, match="language"):
        TesseractOCRAdapter(language="  ")
