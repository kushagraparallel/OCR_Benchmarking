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
