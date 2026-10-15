"""Database-backed OCR benchmark worker process.

Run from backend/: python -m app.workers.benchmark_worker

Workers share a PostgreSQL queue and claim jobs with FOR UPDATE SKIP LOCKED.
Run one worker process per intended concurrent benchmark to keep model memory
predictable. Multiple workers coordinate through leases stored in PostgreSQL.
"""

import asyncio
import logging
import signal
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.core.documents.storage import LocalDocumentStorage
from app.core.ocr.base import OCRAdapter
from app.core.ocr.benchmark import BenchmarkConfig, BenchmarkResult, OCRBenchmarkRunner
from app.core.ocr.pdf_renderer import PDFPageRenderer
from app.core.ocr.registry import OCREngineFactory, create_configured_ocr_factory
from app.db.database import SessionFactory
from app.db.repositories.benchmark_job_repository import BenchmarkJobRepository
from app.db.repositories.benchmark_worker_slot_repository import BenchmarkWorkerSlotRepository
from app.models.benchmark_job import BenchmarkJob
from app.models.document import DocumentRecord

logger = logging.getLogger(__name__)
_STOP_REQUESTED = False
_WORKER_FACTORY: OCREngineFactory | None = None
_WORKER_ADAPTERS: dict[str, OCRAdapter] = {}


def _request_stop(signum: int, frame: object) -> None:
    """Request graceful shutdown after the current job reaches a safe boundary."""
    del signum, frame
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _load_job_inputs(job_id: str) -> tuple[str, list[str], str] | None:
    """Read the source document reference and selected engines in a short transaction."""
    with SessionFactory() as session:
        job = session.get(BenchmarkJob, job_id)
        if job is None:
            return None
        if job.status == "cancellation_requested":
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            job.lease_expires_at = None
            session.commit()
            return None
        if job.status != "running":
            return None
        document = session.scalar(
            select(DocumentRecord).where(DocumentRecord.id == job.document_id)
        )
        if document is None:
            _finish_job(job_id, "failed", error="The source document no longer exists.")
            return None
        return document.storage_key, list(job.engine_names), job.document_id


def _finish_job(
    job_id: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Persist terminal state and release the lease in a fresh transaction."""
    with SessionFactory() as session:
        job = session.get(BenchmarkJob, job_id)
        if job is None:
            return
        if job.status == "cancellation_requested":
            status = "cancelled"
            result = None
            error = None
        job.status = status
        job.result = result
        job.error = error
        job.finished_at = datetime.now(timezone.utc)
        job.lease_expires_at = None
        session.commit()


def _is_cancel_requested(job_id: str) -> bool:
    """Read the durable cancellation flag using a short-lived database session."""
    with SessionFactory() as session:
        job = session.get(BenchmarkJob, job_id)
        return job is None or job.status in {"cancellation_requested", "cancelled"}


def _renew_lease(job_id: str, lease_seconds: int) -> bool:
    """Extend a job lease while the OCR task is active."""
    with SessionFactory() as session:
        return BenchmarkJobRepository(session).renew_lease(job_id, lease_seconds)


async def _lease_heartbeat(job_id: str, slot_id: int, worker_id: str, lease_seconds: int) -> None:
    """Keep long-running jobs from being reclaimed by another worker."""
    interval = max(5.0, lease_seconds / 3)
    while True:
        await asyncio.sleep(interval)
        job_renewed = await asyncio.to_thread(_renew_lease, job_id, lease_seconds)
        slot_renewed = await asyncio.to_thread(
            _renew_worker_slot, slot_id, worker_id, lease_seconds
        )
        if not job_renewed or not slot_renewed:
            return



def _get_worker_adapters(engine_names: list[str]) -> dict[str, OCRAdapter]:
    """Reuse initialized adapter instances for the lifetime of this worker process."""
    global _WORKER_FACTORY
    if _WORKER_FACTORY is None:
        _WORKER_FACTORY = create_configured_ocr_factory()

    available = set(_WORKER_FACTORY.available_engines())
    unknown = sorted(set(engine_names) - available)
    if unknown:
        raise ValueError(f"Unconfigured OCR engine(s): {', '.join(unknown)}.")

    for engine_name in engine_names:
        if engine_name not in _WORKER_ADAPTERS:
            _WORKER_ADAPTERS[engine_name] = _WORKER_FACTORY.create(engine_name)
    return {name: _WORKER_ADAPTERS[name] for name in engine_names}


def _serialize_result(result: BenchmarkResult) -> dict[str, Any]:
    """Convert benchmark dataclasses into JSON-compatible result structures."""
    return asdict(result)


async def _execute_job(job_id: str, concurrency_semaphore: asyncio.Semaphore, slot_id: int, worker_id: str) -> None:
    """Run one claimed job, isolate errors, and persist normalized engine output."""
    settings = get_settings()
    inputs = await asyncio.to_thread(_load_job_inputs, job_id)
    if inputs is None:
        return

    storage_key, engine_names, _document_id = inputs
    storage = LocalDocumentStorage(
        settings.document_storage_root, settings.max_document_upload_bytes
    )
    try:
        pdf_path: Path = storage.resolve_storage_key(storage_key)
        pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
        adapters = _get_worker_adapters(engine_names)
        runner = OCRBenchmarkRunner(
            PDFPageRenderer(
                max_pages=settings.max_pdf_pages,
                max_page_dimension_pixels=10_000,
            ),
            BenchmarkConfig(
                engine_timeout_seconds=settings.ocr_engine_timeout_seconds,
                max_concurrent_engines=settings.ocr_max_concurrent_engines,
                max_total_rendered_image_bytes=settings.ocr_max_rendered_image_bytes,
            ),
            concurrency_semaphore=concurrency_semaphore,
        )
        heartbeat = asyncio.create_task(
            _lease_heartbeat(job_id, slot_id, worker_id, settings.ocr_worker_lease_seconds)
        )
        try:
            result = await runner.run(
                pdf_bytes,
                adapters,
                should_cancel=lambda: asyncio.to_thread(_is_cancel_requested, job_id),
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        terminal_status = result.status
        if terminal_status == "success":
            terminal_status = "completed"
        await asyncio.to_thread(
            _finish_job,
            job_id,
            terminal_status,
            result=_serialize_result(result),
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(_finish_job, job_id, "cancelled")
        return
    except Exception as exc:
        logger.exception("Benchmark job %s failed", job_id)
        await asyncio.to_thread(
            _finish_job,
            job_id,
            "failed",
            error=f"Benchmark execution failed ({type(exc).__name__}).",
        )



def _ensure_worker_capacity() -> None:
    """Provision the configured number of shared execution slots."""
    settings = get_settings()
    with SessionFactory() as session:
        BenchmarkWorkerSlotRepository(session).ensure_capacity(
            settings.ocr_max_concurrent_benchmark_jobs
        )


def _acquire_worker_slot(worker_id: str) -> int | None:
    """Reserve one globally shared benchmark slot."""
    settings = get_settings()
    with SessionFactory() as session:
        return BenchmarkWorkerSlotRepository(session).acquire(
            worker_id,
            settings.ocr_max_concurrent_benchmark_jobs,
            settings.ocr_worker_lease_seconds,
        )


def _renew_worker_slot(slot_id: int, worker_id: str, lease_seconds: int) -> bool:
    """Renew the worker's global concurrency slot."""
    with SessionFactory() as session:
        return BenchmarkWorkerSlotRepository(session).renew(slot_id, worker_id, lease_seconds)


def _release_worker_slot(slot_id: int, worker_id: str) -> None:
    """Release the worker's global concurrency slot."""
    with SessionFactory() as session:
        BenchmarkWorkerSlotRepository(session).release(slot_id, worker_id)


def _claim_next_job() -> tuple[str, int] | None:
    """Claim one job in a short database transaction."""
    settings = get_settings()
    with SessionFactory() as session:
        job = BenchmarkJobRepository(session).claim_next(settings.ocr_worker_lease_seconds)
        if job is None:
            return None
        return job.id, job.attempt_count


async def _worker_loop() -> None:
    """Poll jobs while enforcing shared capacity across all worker processes."""
    settings = get_settings()
    concurrency_semaphore = asyncio.Semaphore(settings.ocr_max_concurrent_engines)
    worker_id = str(uuid4())
    await asyncio.to_thread(_ensure_worker_capacity)

    while not _STOP_REQUESTED:
        slot_id = await asyncio.to_thread(_acquire_worker_slot, worker_id)
        if slot_id is None:
            await asyncio.sleep(settings.ocr_worker_poll_seconds)
            continue

        try:
            claimed = await asyncio.to_thread(_claim_next_job)
            if claimed is None:
                await asyncio.sleep(settings.ocr_worker_poll_seconds)
                continue

            job_id, attempt_count = claimed
            if attempt_count > settings.ocr_worker_max_attempts:
                await asyncio.to_thread(
                    _finish_job,
                    job_id,
                    "failed",
                    error="Benchmark exceeded the maximum worker recovery attempts.",
                )
                continue

            await _execute_job(job_id, concurrency_semaphore, slot_id, worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Benchmark worker loop failed")
            await asyncio.sleep(settings.ocr_worker_poll_seconds)
        finally:
            await asyncio.to_thread(_release_worker_slot, slot_id, worker_id)


def run_worker() -> None:
    """Poll and claim jobs until SIGINT or SIGTERM requests shutdown."""
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    asyncio.run(_worker_loop())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
