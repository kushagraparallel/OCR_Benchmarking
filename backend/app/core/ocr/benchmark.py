"""Resource-bounded orchestration for comparing OCR engines on the same PDF pages."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
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
    """Render each page once and compare engines with bounded worker concurrency.

    Rendering and synchronous OCR execute in worker threads, never on the FastAPI
    event loop. Pages are processed incrementally and their image buffers are
    released before the next page is rendered.
    """

    def __init__(
        self,
        renderer: PDFPageRenderer,
        config: BenchmarkConfig | None = None,
        concurrency_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._renderer = renderer
        self._config = config or BenchmarkConfig()
        self._engine_semaphore = concurrency_semaphore or asyncio.Semaphore(
            self._config.max_concurrent_engines
        )

    async def run(
        self,
        pdf_bytes: bytes,
        adapters: dict[str, OCRAdapter],
        should_cancel: Callable[[], Awaitable[bool]] | None = None,
    ) -> BenchmarkResult:
        """Execute engines independently and preserve successful partial results."""
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
        engine_durations = {name: 0.0 for name in normalized_adapters}
        page_iterator = None
        renderer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr-pdf-render")
        event_loop = asyncio.get_running_loop()

        try:
            page_iterator = await event_loop.run_in_executor(
                renderer_executor, iter, self._renderer.render_pages(pdf_bytes)
            )
            while True:
                if should_cancel is not None and await should_cancel():
                    raise asyncio.CancelledError("Benchmark cancellation requested.")
                page = await event_loop.run_in_executor(
                    renderer_executor, self._next_page, page_iterator
                )
                if page is None:
                    break
                page_count += 1
                rendered_bytes += len(page.image_bytes)
                if rendered_bytes > self._config.max_total_rendered_image_bytes:
                    raise OCRInputError(
                        "Rendered PDF images exceed the configured total image-byte limit."
                    )

                image = OCRImage(page.image_bytes, page.page_number)
                page_task_started = {
                    name: time.perf_counter() for name in active_names
                }
                page_tasks = {
                    name: asyncio.create_task(
                        self._recognize_page(normalized_adapters[name], image)
                    )
                    for name in tuple(active_names)
                }
                outcomes = await asyncio.gather(
                    *page_tasks.values(), return_exceptions=True
                )
                for name, outcome in zip(page_tasks, outcomes, strict=True):
                    engine_durations[name] += (
                        time.perf_counter() - page_task_started[name]
                    ) * 1000
                    if isinstance(outcome, BaseException):
                        result = engine_results[name]
                        result.status = (
                            "timed_out" if isinstance(outcome, TimeoutError) else "failed"
                        )
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
        except OCRInputError:
            raise
        except Exception as exc:
            logger.exception("OCR benchmark could not complete PDF rendering")
            if page_count == 0:
                raise
            for name in active_names:
                engine_results[name].status = "failed"
                engine_results[name].error = self._safe_error_message(exc)
            active_names.clear()
        finally:
            # PyMuPDF's document iterator must be advanced on one consistent thread.
            # Wait for an in-flight page render to finish before shutting its executor down.
            await asyncio.to_thread(
                renderer_executor.shutdown, wait=True, cancel_futures=True
            )

        for name, result in engine_results.items():
            result.duration_ms = round(engine_durations[name], 3)
            if result.status == "success" and not result.results:
                result.status = "failed"
                result.error = "The engine did not return any page results."
            elif result.status == "success" and page_count and len(result.results) < page_count:
                result.status = "partial"

        succeeded = sum(bool(result.results) for result in engine_results.values())
        failed = sum(
            result.status in ("failed", "timed_out")
            for result in engine_results.values()
        )
        if failed == 0 and succeeded == len(engine_results):
            overall_status: Literal["success", "partial", "failed"] = "success"
        elif succeeded:
            overall_status = "partial"
        else:
            overall_status = "failed"

        return BenchmarkResult(
            status=overall_status,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            page_count=page_count,
            engines=engine_results,
        )

    @staticmethod
    def _next_page(page_iterator):
        """Advance a lazy renderer without leaking StopIteration through asyncio."""
        sentinel = object()
        page = next(page_iterator, sentinel)
        return None if page is sentinel else page

    async def _recognize_page(
        self,
        adapter: OCRAdapter,
        image: OCRImage,
    ) -> OCRResult:
        """Run synchronous inference off-loop and preserve slots after timeout/cancel."""
        await self._engine_semaphore.acquire()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, adapter.recognize, image)
        try:
            result = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=self._config.engine_timeout_seconds,
            )
        except (TimeoutError, asyncio.CancelledError):
            # Cancelling an await does not stop native OCR already running in a thread.
            # Keep the slot occupied until that thread has really completed.
            future.add_done_callback(
                lambda _: loop.call_soon_threadsafe(self._engine_semaphore.release)
            )
            raise
        except Exception:
            self._engine_semaphore.release()
            raise
        self._engine_semaphore.release()
        return result

    @staticmethod
    def _validate_adapters(
        adapters: dict[str, OCRAdapter],
    ) -> dict[str, OCRAdapter]:
        """Reject ambiguous names and mismatched adapters before rendering."""
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
        """Return a bounded error description without exposing stack traces."""
        if isinstance(error, TimeoutError):
            return "OCR engine exceeded the configured timeout."
        if isinstance(error, OCRAdapterError):
            return str(error)[:500]
        return f"OCR engine failed ({type(error).__name__})."
