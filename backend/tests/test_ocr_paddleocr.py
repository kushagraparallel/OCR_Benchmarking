"""Unit tests for PaddleOCR normalization and lazy initialization."""

import importlib.metadata
from unittest.mock import Mock, patch

import pytest

from app.core.ocr.errors import OCRDependencyError, OCRExecutionError, OCRInputError
from app.core.ocr.paddleocr import DEFAULT_DETECTION_IMAGE_SIDE_LIMIT, PaddleOCRAdapter
from app.core.ocr.schemas import OCRImage


def create_adapter(tmp_path, **overrides) -> PaddleOCRAdapter:
    """Create an adapter with temporary, pre-provisioned model directories."""
    detection_directory = tmp_path / "detection"
    recognition_directory = tmp_path / "recognition"
    classification_directory = tmp_path / "classification"
    detection_directory.mkdir(exist_ok=True)
    recognition_directory.mkdir(exist_ok=True)
    classification_directory.mkdir(exist_ok=True)
    configuration = {
        "detection_model_directory": detection_directory,
        "recognition_model_directory": recognition_directory,
        "classification_model_directory": classification_directory,
    }
    configuration.update(overrides)
    return PaddleOCRAdapter(**configuration)


def test_adapter_uses_stable_name_and_lazy_engine_initialization(tmp_path) -> None:
    """Creating an adapter must not import PaddleOCR or load models."""
    adapter = create_adapter(tmp_path)

    assert adapter.engine_name == "paddleocr"
    assert adapter._engine is None


def test_constructor_requires_existing_model_directories(tmp_path) -> None:
    """Missing model paths should fail before engine initialization or network access."""
    with pytest.raises(ValueError, match="existing directory"):
        PaddleOCRAdapter(
            detection_model_directory=tmp_path / "missing-det",
            recognition_model_directory=tmp_path / "missing-rec",
            use_angle_classification=False,
        )


def test_get_version_reports_missing_optional_dependency(tmp_path) -> None:
    """Missing optional runtime should be expressed as an OCR dependency error."""
    adapter = create_adapter(tmp_path)
    with patch(
        "app.core.ocr.paddleocr.importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        with pytest.raises(OCRDependencyError, match="PaddleOCR is not installed"):
            adapter.get_version()


def test_get_engine_initializes_once_and_reuses_engine(tmp_path) -> None:
    """The expensive OCR engine should be created only once."""
    adapter = create_adapter(tmp_path)
    fake_engine = Mock()
    fake_module = Mock()
    fake_module.PaddleOCR.return_value = fake_engine

    with patch("app.core.ocr.paddleocr.importlib.import_module", return_value=fake_module):
        assert adapter._get_engine() is fake_engine
        assert adapter._get_engine() is fake_engine

    fake_module.PaddleOCR.assert_called_once_with(
        lang="en",
        use_angle_cls=True,
        use_gpu=False,
        det_model_dir=str((tmp_path / "detection").resolve()),
        rec_model_dir=str((tmp_path / "recognition").resolve()),
        cls_model_dir=str((tmp_path / "classification").resolve()),
        det_limit_side_len=DEFAULT_DETECTION_IMAGE_SIDE_LIMIT,
        show_log=False,
    )


def test_detection_image_side_limit_is_configurable_and_forwarded(tmp_path) -> None:
    """A deployment must be able to override the detector's resize ceiling."""
    adapter = create_adapter(tmp_path, detection_image_side_limit=4000)
    fake_module = Mock()

    with patch("app.core.ocr.paddleocr.importlib.import_module", return_value=fake_module):
        adapter._get_engine()

    assert fake_module.PaddleOCR.call_args.kwargs["det_limit_side_len"] == 4000


def test_detection_image_side_limit_rejects_non_positive_values(tmp_path) -> None:
    """A zero or negative resize ceiling would disable detection entirely."""
    with pytest.raises(ValueError, match="detection_image_side_limit"):
        create_adapter(tmp_path, detection_image_side_limit=0)


def test_normalize_detections_handles_nested_page_result() -> None:
    """Nested PaddleOCR results should become pixel bounds and 0–100 confidence."""
    raw_result = [[
        ([[10, 20], [40, 20], [40, 32], [10, 32]], ("OCRLab", 0.95)),
        ([[5, 4], [15, 4], [15, 14], [5, 14]], ("ready", 0.8)),
    ]]

    words = PaddleOCRAdapter._normalize_detections(raw_result)

    assert [word.text for word in words] == ["OCRLab", "ready"]
    assert words[0].bounding_box.x == 10
    assert words[0].bounding_box.y == 20
    assert words[0].bounding_box.width == 30
    assert words[0].bounding_box.height == 12
    assert words[0].confidence == 95.0


def test_normalize_detections_handles_empty_page() -> None:
    """A valid page with no detections should produce an empty result."""
    assert PaddleOCRAdapter._normalize_detections([None]) == ()
    assert PaddleOCRAdapter._normalize_detections(None) == ()


def test_normalize_detections_rejects_malformed_engine_output() -> None:
    """Malformed results should not be recorded as a successful OCR run."""
    with pytest.raises(OCRExecutionError, match="malformed detection data"):
        PaddleOCRAdapter._normalize_detections([("invalid",)])


def test_normalize_detections_does_not_accept_non_finite_coordinates() -> None:
    """NaN and infinite coordinates must not leak into persisted geometry."""
    raw_result = [[
        ([[float("nan"), 0], [10, 0], [10, 10]], ("bad", 0.5)),
    ]]
    with pytest.raises(OCRExecutionError, match="malformed detection data"):
        PaddleOCRAdapter._normalize_detections(raw_result)


def test_recognize_rejects_invalid_image_before_loading_engine(tmp_path) -> None:
    """Invalid image input should fail before the optional engine is loaded."""
    adapter = create_adapter(tmp_path)
    with pytest.raises(OCRInputError, match="not a readable image"):
        adapter.recognize(OCRImage(b"not-an-image", page_number=1))


def test_adapter_rejects_invalid_configuration(tmp_path) -> None:
    """Invalid language, pixel limit, or classification configuration fails early."""
    with pytest.raises(ValueError, match="language"):
        create_adapter(tmp_path, language=" ")
    with pytest.raises(ValueError, match="max_image_pixels"):
        create_adapter(tmp_path, max_image_pixels=0)
    with pytest.raises(ValueError, match="classification_model_directory"):
        PaddleOCRAdapter(
            detection_model_directory=tmp_path,
            recognition_model_directory=tmp_path,
            use_angle_classification=True,
        )
