"""Registry and factory for configured OCR engine adapters."""

from collections.abc import Callable, Iterable
from typing import Any

from app.core.ocr.base import OCRAdapter


AdapterBuilder = Callable[[], OCRAdapter]


class OCREngineFactory:
    """Create named OCR adapters without coupling orchestration to engine packages."""

    def __init__(self) -> None:
        self._builders: dict[str, AdapterBuilder] = {}

    def register(self, name: str, builder: AdapterBuilder) -> None:
        """Register an adapter builder under a stable, case-insensitive name."""
        normalized_name = name.strip().casefold()
        if not normalized_name:
            raise ValueError("Engine name must not be empty.")
        if not callable(builder):
            raise ValueError("Engine builder must be callable.")
        if normalized_name in self._builders:
            raise ValueError(f"OCR engine '{normalized_name}' is already registered.")
        self._builders[normalized_name] = builder

    def available_engines(self) -> tuple[str, ...]:
        """Return registered engine names in deterministic order."""
        return tuple(sorted(self._builders))

    def create(self, name: str) -> OCRAdapter:
        """Build one adapter or raise a clear error for an unknown engine."""
        normalized_name = name.strip().casefold()
        if normalized_name not in self._builders:
            available = ", ".join(self.available_engines()) or "(none)"
            raise ValueError(
                f"Unknown OCR engine '{name}'. Available engines: {available}."
            )
        adapter = self._builders[normalized_name]()
        if not isinstance(adapter, OCRAdapter):
            raise TypeError(f"Builder for '{normalized_name}' did not return an OCRAdapter.")
        if adapter.engine_name.casefold() != normalized_name:
            raise ValueError(
                f"Registered name '{normalized_name}' does not match adapter "
                f"name '{adapter.engine_name}'."
            )
        return adapter

    def create_many(self, names: Iterable[str]) -> dict[str, OCRAdapter]:
        """Validate all requested names before constructing any adapters."""
        requested = tuple(name.strip().casefold() for name in names)
        if not requested:
            raise ValueError("At least one OCR engine must be selected.")
        if any(not name for name in requested):
            raise ValueError("OCR engine names must not be empty.")
        if len(set(requested)) != len(requested):
            raise ValueError("Duplicate OCR engine names are not allowed.")
        unknown = sorted(set(requested) - self._builders.keys())
        if unknown:
            available = ", ".join(self.available_engines()) or "(none)"
            raise ValueError(
                f"Unknown OCR engine(s): {', '.join(unknown)}. "
                f"Available engines: {available}."
            )
        return {name: self.create(name) for name in requested}


def create_default_ocr_factory(
    *,
    tesseract_options: dict[str, Any] | None = None,
    easyocr_options: dict[str, Any] | None = None,
    paddleocr_options: dict[str, Any] | None = None,
    doctr_predictor_factory: Callable[[], Any] | None = None,
) -> OCREngineFactory:
    """Register supported adapters; optional engines are constructed lazily.

    Optional engines must be explicitly configured. This prevents implicit model
    downloads and avoids importing heavyweight runtimes when the factory is created.
    """
    from app.core.ocr.tesseract import TesseractOCRAdapter

    factory = OCREngineFactory()
    factory.register(
        "tesseract",
        lambda: TesseractOCRAdapter(**(tesseract_options or {})),
    )

    if easyocr_options is not None:
        from app.core.ocr.easyocr import EasyOCRAdapter

        factory.register("easyocr", lambda: EasyOCRAdapter(**easyocr_options))

    if paddleocr_options is not None:
        from app.core.ocr.paddleocr import PaddleOCRAdapter

        factory.register("paddleocr", lambda: PaddleOCRAdapter(**paddleocr_options))

    if doctr_predictor_factory is not None:
        from app.core.ocr.doctr import DocTRAdapter

        factory.register("doctr", lambda: DocTRAdapter(doctr_predictor_factory))

    return factory


def create_configured_ocr_factory() -> OCREngineFactory:
    """Build the API/worker engine registry from explicit deployment settings.

    Optional engines are exposed only when selected in configuration and their
    local model assets are provisioned. The docTR adapter remains opt-in through
    an application-supplied predictor factory and is therefore not enabled here.
    """
    from app.config import get_settings

    settings = get_settings()
    enabled = {name.strip().casefold() for name in settings.ocr_enabled_engines}
    supported = {"tesseract", "easyocr", "paddleocr"}
    unsupported = enabled - supported
    if unsupported:
        raise ValueError(
            "Unsupported configured OCR engine(s): " + ", ".join(sorted(unsupported))
        )

    factory = OCREngineFactory()
    if "tesseract" in enabled:
        from app.core.ocr.tesseract import TesseractOCRAdapter

        factory.register("tesseract", TesseractOCRAdapter)

    if "easyocr" in enabled:
        if settings.ocr_easyocr_model_directory is None:
            raise ValueError(
                "OCR_EASYOCR_MODEL_DIRECTORY is required when EasyOCR is enabled."
            )
        from app.core.ocr.easyocr import EasyOCRAdapter

        factory.register(
            "easyocr",
            lambda: EasyOCRAdapter(
                model_storage_directory=settings.ocr_easyocr_model_directory,
                download_enabled=False,
            ),
        )

    if "paddleocr" in enabled:
        model_paths = (
            settings.ocr_paddle_detection_model_directory,
            settings.ocr_paddle_recognition_model_directory,
            settings.ocr_paddle_classification_model_directory,
        )
        if any(path is None for path in model_paths):
            raise ValueError(
                "All three PaddleOCR model directories must be configured when "
                "PaddleOCR is enabled."
            )
        from app.core.ocr.paddleocr import PaddleOCRAdapter

        factory.register(
            "paddleocr",
            lambda: PaddleOCRAdapter(
                detection_model_directory=settings.ocr_paddle_detection_model_directory,
                recognition_model_directory=settings.ocr_paddle_recognition_model_directory,
                classification_model_directory=settings.ocr_paddle_classification_model_directory,
            ),
        )

    if not factory.available_engines():
        raise ValueError("At least one OCR engine must be enabled.")
    return factory
