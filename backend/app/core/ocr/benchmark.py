"""Resource-bounded orchestration for comparing OCR engines on the same PDF pages."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal

from app.core.ocr.base import OCRAdapter
from app.core.ocr.errors import OCRAdapterError, OCRInputError
from app.core.ocr.pdf_renderer import PDFPageRenderer, RenderedPDFPage
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
        self._pending_native_calls: set[asyncio.Future[OCRResult]] = set()
        self._native_calls_drained = asyncio.Event()
        self._native_calls_drained.set()

    async def wait_for_native_calls(self) -> None:
        """Block until every in-flight native OCR call has released its capacity slot.

        A cancelled or timed-out ``run()`` can return while an adapter's worker
        thread is still executing. Callers that release shared deployment-wide
        capacity right after ``run()`` must await this first.
        """
        await self._native_calls_drained.wait()

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
                page_task_elapsed: dict[str, float] = {}
                page_tasks = {
                    name: asyncio.create_task(
                        self._recognize_page_and_record_duration(
                            name, normalized_adapters[name], image, page_task_elapsed
                        )
                    )
                    for name in tuple(active_names)
                }
                outcomes = await asyncio.gather(
                    *page_tasks.values(), return_exceptions=True
                )
                for name, outcome in zip(page_tasks, outcomes, strict=True):
                    engine_durations[name] += page_task_elapsed[name] * 1000
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
    def _next_page(page_iterator: Iterator[RenderedPDFPage]) -> RenderedPDFPage | None:
        """Advance a lazy renderer without leaking StopIteration through asyncio."""
        sentinel = object()
        page = next(page_iterator, sentinel)
        return None if page is sentinel else page

    async def _recognize_page_and_record_duration(
        self,
        name: str,
        adapter: OCRAdapter,
        image: OCRImage,
        elapsed_store: dict[str, float],
    ) -> OCRResult:
        """Run one engine's recognition and record its own elapsed time in seconds.

        Every engine's task for a page is awaited together via one
        ``asyncio.gather()`` call. Timing each one from a shared reference point
        measured *after* that gather resolves would record how long the
        slowest sibling engine took, not this engine's own duration. Recording
        elapsed time here, at the moment this task itself finishes (success,
        failure, or cancellation), keeps per-engine timing independent.
        """
        started = time.perf_counter()
        try:
            return await self._recognize_page(adapter, image)
        finally:
            elapsed_store[name] = time.perf_counter() - started

    async def _recognize_page(
        self,
        adapter: OCRAdapter,
        image: OCRImage,
    ) -> OCRResult:
        """Run synchronous inference off-loop and keep capacity until native work exits."""
        await self._engine_semaphore.acquire()
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, adapter.recognize, image)
        self._pending_native_calls.add(future)
        self._native_calls_drained.clear()

        def release_capacity(completed_future: asyncio.Future[OCRResult]) -> None:
            """Release the shared inference slot only when the worker thread is done."""
            self._pending_native_calls.discard(completed_future)
            self._engine_semaphore.release()
            if not self._pending_native_calls:
                self._native_calls_drained.set()

        future.add_done_callback(release_capacity)
        return await asyncio.wait_for(
            asyncio.shield(future),
            timeout=self._config.engine_timeout_seconds,
        )

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
