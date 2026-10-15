"""Unit tests for docTR normalization and lazy predictor initialization."""

import importlib.metadata
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image
import pytest

from app.core.ocr.doctr import DocTRAdapter
from app.core.ocr.errors import OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.schemas import OCRImage


def create_png_bytes() -> bytes:
    """Create a small deterministic PNG image in memory."""
    image = Image.new("RGB", (100, 80), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_adapter_uses_stable_name_and_lazy_predictor() -> None:
    """Constructing the adapter must not load docTR or initialize model weights."""
    factory = Mock()
    adapter = DocTRAdapter(predictor_factory=factory)

    assert adapter.engine_name == "doctr"
    assert adapter._predictor is None
    factory.assert_not_called()


def test_adapter_rejects_invalid_configuration() -> None:
    """Invalid factories and pixel limits should fail during construction."""
    with pytest.raises(ValueError, match="predictor_factory"):
        DocTRAdapter(predictor_factory=None)
    with pytest.raises(ValueError, match="max_image_pixels"):
        DocTRAdapter(predictor_factory=Mock(), max_image_pixels=0)


def test_get_version_reports_missing_optional_dependency() -> None:
    """Missing python-doctr should become a clear domain dependency error."""
    adapter = DocTRAdapter(predictor_factory=Mock())
    with patch(
        "app.core.ocr.doctr.importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        with pytest.raises(OCRDependencyError, match="docTR is not installed"):
            adapter.get_version()


def test_get_predictor_initializes_once_and_reuses_predictor() -> None:
    """The expensive predictor factory should only run once."""
    predictor = Mock()
    factory = Mock(return_value=predictor)
    adapter = DocTRAdapter(predictor_factory=factory)

    with patch("app.core.ocr.doctr.importlib.import_module"):
        assert adapter._get_predictor() is predictor
        assert adapter._get_predictor() is predictor

    factory.assert_called_once_with()


def test_normalize_export_converts_geometry_and_confidence() -> None:
    """Normalized geometry should be scaled from relative coordinates to pixels."""
    exported = {
        "pages": [
            {
                "dimensions": [80, 100],
                "blocks": [
                    {
                        "lines": [
                            {
                                "words": [
                                    {
                                        "value": "OCRLab",
                                        "geometry": [[0.1, 0.25], [0.4, 0.5]],
                                        "confidence": 0.95,
                                    },
                                    {
                                        "value": "ready",
                                        "geometry": [[0.5, 0.1], [0.8, 0.2]],
                                        "confidence": 0.8,
                                    },
                                ]
                            }
                        ]
                    }
                ],
            }
        ]
    }

    words = DocTRAdapter._normalize_export(exported)

    assert [word.text for word in words] == ["OCRLab", "ready"]
    assert words[0].bounding_box.x == 10
    assert words[0].bounding_box.y == 20
    assert words[0].bounding_box.width == 30
    assert words[0].bounding_box.height == 20
    assert words[0].confidence == 95.0


def test_normalize_export_handles_empty_pages() -> None:
    """Valid empty document results should not be treated as engine failures."""
    assert DocTRAdapter._normalize_export({"pages": []}) == ()
    assert DocTRAdapter._normalize_export(
        {"pages": [{"dimensions": [80, 100], "blocks": []}]}
    ) == ()


def test_normalize_export_rejects_malformed_or_non_finite_data() -> None:
    """Invalid geometry and export structure should raise domain execution errors."""
    with pytest.raises(OCRExecutionError, match="malformed document data"):
        DocTRAdapter._normalize_export([])
    with pytest.raises(OCRExecutionError, match="malformed word data"):
        DocTRAdapter._normalize_export(
            {
                "pages": [
                    {
                        "dimensions": [80, 100],
                        "blocks": [{"lines": [{"words": [{
                            "value": "invalid",
                            "geometry": [[float("nan"), 0], [1, 1]],
                            "confidence": 0.5,
                        }]}]}],
                    }
                ]
            }
        )


def test_recognize_rejects_invalid_image_before_loading_predictor() -> None:
    """Invalid bytes should be rejected before optional model initialization."""
    factory = Mock()
    adapter = DocTRAdapter(predictor_factory=factory)

    with pytest.raises(OCRInputError, match="not a readable image"):
        adapter.recognize(OCRImage(b"not-an-image", page_number=1))

    factory.assert_not_called()


def test_recognize_uses_predictor_and_returns_normalized_result() -> None:
    """Recognition should use the shared result contract and preserve page identity."""
    image_bytes = create_png_bytes()
    prediction = Mock()
    prediction.export.return_value = {
        "pages": [
            {
                "dimensions": [80, 100],
                "blocks": [
                    {
                        "lines": [
                            {
                                "words": [
                                    {
                                        "value": "OCRLab",
                                        "geometry": [[0.1, 0.25], [0.4, 0.5]],
                                        "confidence": 0.95,
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        ]
    }
    predictor = Mock(return_value=prediction)
    adapter = DocTRAdapter(predictor_factory=Mock(return_value=predictor))

    with (
        patch("app.core.ocr.doctr.importlib.metadata.version", return_value="0.10.0"),
        patch("app.core.ocr.doctr.importlib.import_module") as import_module,
    ):
        doctr_io = Mock()
        doctr_io.DocumentFile.from_images.return_value = object()
        import_module.side_effect = lambda name: (
            doctr_io if name == "doctr.io" else Mock()
        )
        result = adapter.recognize(OCRImage(image_bytes, page_number=3))

    assert result.engine_name == "doctr"
    assert result.engine_version == "0.10.0"
    assert result.page_number == 3
    assert result.text == "OCRLab"
    assert result.words[0].confidence == 95.0
    assert result.duration_ms >= 0
    doctr_io.DocumentFile.from_images.assert_called_once_with([image_bytes])
