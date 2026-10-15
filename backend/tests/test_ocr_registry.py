"""Unit tests for building the deployment-configured OCR engine registry."""

from types import SimpleNamespace

import pytest

import app.config as config_module
from app.core.ocr.doctr import DocTRAdapter
from app.core.ocr.registry import create_configured_ocr_factory


def _settings(**overrides: object) -> SimpleNamespace:
    """Build a minimal settings stand-in with every OCR field defaulted."""
    base = {
        "ocr_enabled_engines": ["tesseract"],
        "ocr_easyocr_model_directory": None,
        "ocr_paddle_detection_model_directory": None,
        "ocr_paddle_recognition_model_directory": None,
        "ocr_paddle_classification_model_directory": None,
        "ocr_doctr_det_arch": "db_resnet50",
        "ocr_doctr_reco_arch": "crnn_vgg16_bn",
        "ocr_doctr_cache_directory": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_unsupported_engine_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An engine name outside the supported set must fail fast with its name listed."""
    monkeypatch.setattr(config_module, "get_settings", lambda: _settings(ocr_enabled_engines=["not-a-real-engine"]))

    with pytest.raises(ValueError, match="not-a-real-engine"):
        create_configured_ocr_factory()


def test_doctr_requires_cache_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enabling docTR without a provisioned weights cache must fail at factory build time."""
    monkeypatch.setattr(config_module, "get_settings", lambda: _settings(ocr_enabled_engines=["doctr"]))

    with pytest.raises(ValueError, match="OCR_DOCTR_CACHE_DIRECTORY"):
        create_configured_ocr_factory()


def test_doctr_registers_without_importing_the_doctr_package(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Building and creating the adapter must stay lazy; only recognize()/get_version() touch doctr."""
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: _settings(ocr_enabled_engines=["doctr"], ocr_doctr_cache_directory=tmp_path),
    )

    factory = create_configured_ocr_factory()

    assert factory.available_engines() == ("doctr",)
    adapter = factory.create("doctr")
    assert isinstance(adapter, DocTRAdapter)
    assert adapter._predictor is None


def test_easyocr_requires_model_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enabling EasyOCR without a provisioned model directory must fail at factory build time."""
    monkeypatch.setattr(config_module, "get_settings", lambda: _settings(ocr_enabled_engines=["easyocr"]))

    with pytest.raises(ValueError, match="OCR_EASYOCR_MODEL_DIRECTORY"):
        create_configured_ocr_factory()


def test_paddleocr_requires_all_three_model_directories(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Partial PaddleOCR model configuration must fail rather than silently degrade."""
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: _settings(
            ocr_enabled_engines=["paddleocr"],
            ocr_paddle_detection_model_directory=tmp_path,
        ),
    )

    with pytest.raises(ValueError, match="All three PaddleOCR model directories"):
        create_configured_ocr_factory()


def test_multiple_engines_register_together(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A deployment can enable several engines at once; each becomes independently selectable."""
    monkeypatch.setattr(
        config_module,
        "get_settings",
        lambda: _settings(
            ocr_enabled_engines=["tesseract", "doctr"],
            ocr_doctr_cache_directory=tmp_path,
        ),
    )

    factory = create_configured_ocr_factory()

    assert factory.available_engines() == ("doctr", "tesseract")
