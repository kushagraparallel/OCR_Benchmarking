"""Unit tests for the optional EasyOCR adapter without downloading models."""

from unittest.mock import Mock, patch

from PIL import Image
import pytest

from app.core.ocr.errors import OCRDependencyError, OCRInputError
from app.core.ocr.easyocr import EasyOCRAdapter
from app.core.ocr.schemas import OCRImage


def test_adapter_uses_stable_name_and_lazy_reader_initialization() -> None:
    """Creating an adapter must not import EasyOCR or initialize its models."""
    adapter = EasyOCRAdapter()
    assert adapter.engine_name == "easyocr"
    assert adapter._reader is None


def test_get_version_reports_missing_optional_dependency() -> None:
    """A missing EasyOCR installation should raise a clear domain dependency error."""
    adapter = EasyOCRAdapter()
    with patch(
        "app.core.ocr.easyocr.importlib.metadata.version",
        side_effect=__import__("importlib").metadata.PackageNotFoundError,
    ):
        with pytest.raises(OCRDependencyError, match="EasyOCR is not installed"):
            adapter.get_version()


def test_get_reader_initializes_once_and_reuses_reader() -> None:
    """Model initialization is expensive and must be reused across pages."""
    adapter = EasyOCRAdapter(languages=("en",), download_enabled=False)
    fake_reader = Mock()
    fake_easyocr = Mock()
    fake_easyocr.Reader.return_value = fake_reader

    with patch("app.core.ocr.easyocr.importlib.import_module", return_value=fake_easyocr):
        assert adapter._get_reader() is fake_reader
        assert adapter._get_reader() is fake_reader

    fake_easyocr.Reader.assert_called_once_with(
        ["en"],
        gpu=False,
        model_storage_directory=None,
        download_enabled=False,
    )


def test_normalize_detections_converts_polygon_and_confidence() -> None:
    """EasyOCR polygons should become pixel rectangles and normalized confidence."""
    detections = [
        ([[10, 20], [40, 20], [40, 32], [10, 32]], "OCRLab", 0.95),
        ([[5, 4], [15, 4], [15, 14], [5, 14]], "ready", 0.8),
    ]

    words = EasyOCRAdapter._normalize_detections(detections)

    assert [word.text for word in words] == ["OCRLab", "ready"]
    assert words[0].bounding_box.x == 10
    assert words[0].bounding_box.y == 20
    assert words[0].bounding_box.width == 30
    assert words[0].bounding_box.height == 12
    assert words[0].confidence == 0.95


def test_normalize_detections_rejects_malformed_data() -> None:
    """Unexpected engine output must not be silently recorded as a successful result."""
    with pytest.raises(Exception, match="malformed detection data"):
        EasyOCRAdapter._normalize_detections([("bad",)])


def test_recognize_rejects_invalid_image_before_loading_model() -> None:
    """Invalid input should fail before model loading or inference."""
    adapter = EasyOCRAdapter()
    with pytest.raises(OCRInputError, match="not a readable image"):
        adapter.recognize(OCRImage(b"not-an-image", page_number=1))


def test_adapter_rejects_invalid_configuration() -> None:
    """Language and pixel-limit configuration should be validated early."""
    with pytest.raises(ValueError, match="languages"):
        EasyOCRAdapter(languages=())
    with pytest.raises(ValueError, match="max_image_pixels"):
        EasyOCRAdapter(max_image_pixels=0)
