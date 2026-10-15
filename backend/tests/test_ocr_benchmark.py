"""Tests for OCR engine registration and bounded benchmark orchestration."""

import asyncio
import io
import threading
import time

import fitz
import pytest

from app.core.ocr.base import OCRAdapter
from app.core.ocr.benchmark import BenchmarkConfig, OCRBenchmarkRunner
from app.core.ocr.errors import OCRExecutionError, OCRInputError
from app.core.ocr.pdf_renderer import PDFPageRenderer, RenderedPDFPage
from app.core.ocr.registry import OCREngineFactory
from app.core.ocr.schemas import OCRBoundingBox, OCRImage, OCRResult, OCRWord


class FakeAdapter(OCRAdapter):
    """Deterministic synchronous adapter for orchestration tests."""

    def __init__(self, name: str, *, delay: float = 0, fail: bool = False) -> None:
        self._name = name
        self.delay = delay
        self.fail = fail
        self.seen_images: list[bytes] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        return self._name

    def get_version(self) -> str:
        return "test"

    def recognize(self, image: OCRImage) -> OCRResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.seen_images.append(image.image_bytes)
            if self.delay:
                time.sleep(self.delay)
            if self.fail:
                raise OCRExecutionError("simulated engine failure")
            word = OCRWord("hello", OCRBoundingBox(0, 0, 10, 5), 99.0)
            return OCRResult(
                engine_name=self.engine_name,
                engine_version="test",
                page_number=image.page_number,
                text="hello",
                words=(word,),
                duration_ms=1.0,
            )
        finally:
            with self._lock:
                self.active -= 1


class FakeRenderer:
    """Yield predictable page images and count renders."""

    def __init__(self, pages: int = 2, image_bytes: bytes = b"same-page-image") -> None:
        self.pages = pages
        self.image_bytes = image_bytes
        self.rendered = 0

    def render_pages(self, pdf_bytes: bytes):
        for page_number in range(1, self.pages + 1):
            self.rendered += 1
            yield RenderedPDFPage(page_number, self.image_bytes, 10, 10, 72)


def create_pdf(page_count: int) -> bytes:
    """Build a tiny PDF entirely in memory."""
    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


def test_factory_validates_names_before_building_adapters() -> None:
    """Unknown and duplicate engines are rejected before any factory call."""
    factory = OCREngineFactory()
    calls = []
    factory.register("fake", lambda: calls.append(True) or FakeAdapter("fake"))

    with pytest.raises(ValueError, match="Unknown OCR engine"):
        factory.create_many(["fake", "missing"])
    with pytest.raises(ValueError, match="Duplicate"):
        factory.create_many(["fake", "FAKE"])
    assert calls == []
    assert factory.create_many(["FAKE"])["fake"].engine_name == "fake"


@pytest.mark.asyncio
async def test_partial_engine_failure_preserves_other_engine_results() -> None:
    """A failing adapter must not discard the successful adapter's normalized output."""
    renderer = FakeRenderer()
    runner = OCRBenchmarkRunner(renderer)
    good, bad = FakeAdapter("good"), FakeAdapter("bad", fail=True)

    result = await runner.run(b"pdf", {"good": good, "bad": bad})

    assert result.status == "partial"
    assert result.page_count == 2
    assert result.engines["good"].status == "success"
    assert [page.text for page in result.engines["good"].results] == ["hello", "hello"]
    assert result.engines["bad"].status == "failed"
    assert "simulated engine failure" in result.engines["bad"].error
    assert renderer.rendered == 2


@pytest.mark.asyncio
async def test_same_rendered_page_bytes_are_shared_across_engines() -> None:
    """Every engine receives the exact same encoded image for each page."""
    renderer = FakeRenderer(pages=3, image_bytes=b"identical")
    runner = OCRBenchmarkRunner(renderer)
    first, second = FakeAdapter("first"), FakeAdapter("second")

    await runner.run(b"pdf", {"first": first, "second": second})

    assert first.seen_images == second.seen_images == [b"identical"] * 3
    assert renderer.rendered == 3


@pytest.mark.asyncio
async def test_concurrency_is_bounded() -> None:
    """Concurrent inference never exceeds the configured global runner limit."""
    renderer = FakeRenderer(pages=1)
    runner = OCRBenchmarkRunner(
        renderer,
        BenchmarkConfig(engine_timeout_seconds=2, max_concurrent_engines=1),
    )
    adapters = {name: FakeAdapter(name, delay=0.02) for name in ("a", "b", "c")}

    await runner.run(b"pdf", adapters)

    assert sum(adapter.max_active for adapter in adapters.values()) == 3
    assert all(adapter.max_active == 1 for adapter in adapters.values())


@pytest.mark.asyncio
async def test_timeout_is_recorded_and_other_engine_succeeds() -> None:
    """An engine timeout is isolated and does not block a healthy engine result."""
    renderer = FakeRenderer(pages=1)
    runner = OCRBenchmarkRunner(
        renderer,
        BenchmarkConfig(engine_timeout_seconds=0.02, max_concurrent_engines=2),
    )
    slow, fast = FakeAdapter("slow", delay=0.15), FakeAdapter("fast")

    result = await runner.run(b"pdf", {"slow": slow, "fast": fast})

    assert result.status == "partial"
    assert result.engines["slow"].status == "timed_out"
    assert result.engines["fast"].status == "success"


@pytest.mark.asyncio
async def test_cancellation_propagates_without_becoming_engine_failure() -> None:
    """Cancelling a benchmark propagates cancellation to its caller."""
    runner = OCRBenchmarkRunner(FakeRenderer(), BenchmarkConfig(engine_timeout_seconds=5))
    task = asyncio.create_task(runner.run(b"pdf", {"slow": FakeAdapter("slow", delay=0.2)}))
    await asyncio.sleep(0.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_rendered_image_budget_is_enforced() -> None:
    """An oversized aggregate raster payload is rejected before OCR starts."""
    runner = OCRBenchmarkRunner(
        FakeRenderer(pages=2, image_bytes=b"123456"),
        BenchmarkConfig(max_total_rendered_image_bytes=10),
    )
    adapter = FakeAdapter("fake")

    with pytest.raises(OCRInputError, match="total image-byte limit"):
        await runner.run(b"pdf", {"fake": adapter})
    assert adapter.seen_images == []


def test_real_renderer_rejects_oversized_pdf_before_page_rendering() -> None:
    """The page-count cap rejects oversized PDFs before allocating page images."""
    renderer = PDFPageRenderer(max_pages=1)
    with pytest.raises(OCRInputError, match="limit is 1"):
        list(renderer.render_pages(create_pdf(page_count=2)))


def test_runner_rejects_adapter_name_mismatch_before_rendering() -> None:
    """Mismatched factory keys are configuration errors, not benchmark failures."""
    renderer = FakeRenderer()
    runner = OCRBenchmarkRunner(renderer)
    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(runner.run(b"pdf", {"wrong": FakeAdapter("right")}))
    assert renderer.rendered == 0


def test_invalid_benchmark_configuration_is_rejected() -> None:
    """Invalid concurrency, timeout, and image budgets fail at construction."""
    with pytest.raises(ValueError, match="engine_timeout_seconds"):
        BenchmarkConfig(engine_timeout_seconds=0)
    with pytest.raises(ValueError, match="max_concurrent_engines"):
        BenchmarkConfig(max_concurrent_engines=0)
    with pytest.raises(ValueError, match="max_total_rendered_image_bytes"):
        BenchmarkConfig(max_total_rendered_image_bytes=0)
