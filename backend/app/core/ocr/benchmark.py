"""Resource-bounded orchestration for comparing OCR engines on the same PDF pages."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRAdapterError, OCRInputError
from app.core.ocr.pdf_renderer import PDFPageRenderer
from app.core.ocr.schemas import OCRImage, OCRResult

logger = logging.getLogger(__name__)

EngineStatus = Literal["success", "partial", "failed", "timed_out"]


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Validated resource limits for one in-process benchmark."""

    engine_timeout_seconds: float = 60.0
    max_concurrent_engines: int = 1
    max_total_rendered_image_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.engine_timeout_seconds <= 0:
            raise ValueError("engine_timeout_seconds must be greater than zero.")
        if self.max_concurrent_engines < 1:
            raise ValueError("max_concurrent_engines must be at least one.")
        if self.max_total_rendered_image_bytes < 1:
            raise ValueError("max_total_rendered_image_bytes must be positive.")


@dataclass(slots=True)
class EngineBenchmarkResult:
    """Outcome and normalized page results for one selected engine."""

    engine_name: str
    status: EngineStatus = "success"
    duration_ms: float = 0.0
    results: list[OCRResult] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class BenchmarkResult:
    """Complete benchmark outcome, including independent engine results."""

    status: Literal["success", "partial", "failed"]
    duration_ms: float
    page_count: int
    engines: dict[str, EngineBenchmarkResult]


class OCRBenchmarkRunner:
    """Render each PDF page once and compare selected engines under bounded concurrency.

    Rendering and OCR are moved to worker threads so synchronous PyMuPDF and OCR
    calls do not block the FastAPI event loop. Page images are released after all
    selected engines have handled that page, avoiding a document-sized image cache.
    """

    def __init__(
        self,
        renderer: PDFPageRenderer,
        config: BenchmarkConfig | None = None,
    ) -> None:
        self._renderer = renderer
        self._config = config or BenchmarkConfig()
        self._engine_semaphore = asyncio.Semaphore(
            self._config.max_concurrent_engines
        )

    async def run(
        self,
        pdf_bytes: bytes,
        adapters: dict[str, OCRAdapter],
    ) -> BenchmarkResult:
        """Execute engines independently and return successful outputs even on failures."""
        if not adapters:
            raise ValueError("At least one OCR engine must be selected.")
        normalized_adapters = self._validate_adapters(adapters)
        started = time.perf_counter()
        engine_results = {
            name: EngineBenchmarkResult(engine_name=name)
            for name in normalized_adapters
        }
        active_names = set(normalized_adapters)
        page_count = 0
        rendered_bytes = 0

        try:
            pages = await asyncio.to_thread(
                self._render_all_pages, pdf_bytes
            )
            # Keep a bounded image budget and render only once per source page.
            for page in pages:
                page_count += 1
                rendered_bytes += len(page.image_bytes)
                if rendered_bytes > self._config.max_total_rendered_image_bytes:
                    raise OCRInputError(
                        "Rendered PDF images exceed the configured total image-byte limit."
                    )
                image = OCRImage(page.image_bytes, page.page_number)
                tasks = {
                    name: asyncio.create_task(
                        self._recognize_page(normalized_adapters[name], image)
                    )
                    for name in tuple(active_names)
                }
                outcomes = await asyncio.gather(*tasks.items(), return_exceptions=True)
                for name, outcome in outcomes:
                    if isinstance(outcome, BaseException):
                        result = engine_results[name]
                        result.status = "timed_out" if isinstance(outcome, TimeoutError) else "failed"
                        result.error = self._safe_error_message(outcome)
                        active_names.discard(name)
                        logger.warning(
                            "OCR engine %s failed on page %s: %s",
                            name,
                            page.page_number,
                            result.error,
                        )
                    else:
                        engine_results[name].results.append(outcome)
        except asyncio.CancelledError:
            logger.info("OCR benchmark cancelled")
            raise
        except Exception as exc:
            logger.exception("OCR benchmark could not complete PDF rendering")
            if not page_count:
                raise
            for name in active_names:
                engine_results[name].status = "failed"
                engine_results[name].error = self._safe_error_message(exc)
            active_names.clear()
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            for result in engine_results.values():
                result.duration_ms = round(elapsed_ms, 3)

        for result in engine_results.values():
            if result.status == "success" and not result.results:
                result.status = "failed"
                result.error = "The engine did not return any page results."
            elif result.status == "success" and page_count and len(result.results) < page_count:
                result.status = "partial"

        successful = sum(bool(result.results) for result in engine_results.values())
        failed = sum(result.status in ("failed", "timed_out") for result in engine_results.values())
        overall_status: Literal["success", "partial", "failed"]
        if failed == 0 and successful == len(engine_results):
            overall_status = "success"
        elif successful:
            overall_status = "partial"
        else:
            overall_status = "failed"
        return BenchmarkResult(
            status=overall_status,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            page_count=page_count,
            engines=engine_results,
        )

    def _render_all_pages(self, pdf_bytes: bytes):
        """Render to a bounded list so total raster memory is checked before OCR."""
        pages = list(self._renderer.render_pages(pdf_bytes))
        if not pages:
            raise OCRInputError("The PDF does not contain any renderable pages.")
        return pages

    async def _recognize_page(
        self,
        adapter: OCRAdapter,
        image: OCRImage,
    ) -> OCRResult:
        """Run synchronous engine work off-loop with per-engine timeout and concurrency."""
        async with self._engine_semaphore:
            return await asyncio.wait_for(
                asyncio.to_thread(adapter.recognize, image),
                timeout=self._config.engine_timeout_seconds,
            )

    @staticmethod
    def _validate_adapters(
        adapters: dict[str, OCRAdapter],
    ) -> dict[str, OCRAdapter]:
        """Reject ambiguous names and mismatched adapters before doing expensive work."""
        normalized: dict[str, OCRAdapter] = {}
        for name, adapter in adapters.items():
            key = name.strip().casefold()
            if not key:
                raise ValueError("OCR engine names must not be empty.")
            if key in normalized:
                raise ValueError(f"Duplicate OCR engine name '{key}'.")
            if not isinstance(adapter, OCRAdapter):
                raise TypeError(f"Engine '{key}' does not implement OCRAdapter.")
            if adapter.engine_name.casefold() != key:
                raise ValueError(
                    f"Engine key '{key}' does not match adapter '{adapter.engine_name}'."
                )
            normalized[key] = adapter
        return normalized

    @staticmethod
    def _safe_error_message(error: BaseException) -> str:
        """Return a bounded error description without exposing stack traces to clients."""
        if isinstance(error, TimeoutError):
            return "OCR engine exceeded the configured timeout."
        if isinstance(error, OCRAdapterError):
            return str(error)[:500]
        return f"OCR engine failed ({type(error).__name__})."
