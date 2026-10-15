"""Database-backed OCR benchmark worker process.

Run from backend/: python -m app.workers.benchmark_worker

Workers share a PostgreSQL queue and claim jobs with FOR UPDATE SKIP LOCKED.
Run one worker process per intended concurrent benchmark to keep model memory
predictable. Multiple workers coordinate through leases stored in PostgreSQL.
"""

import asyncio
import logging
import signal
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.documents.storage import LocalDocumentStorage
from app.core.ocr.benchmark import BenchmarkConfig, OCRBenchmarkRunner
from app.core.ocr.pdf_renderer import PDFPageRenderer
from app.core.ocr.registry import create_default_ocr_factory
from app.db.database import SessionFactory
from app.db.repositories.benchmark_job_repository import BenchmarkJobRepository
from app.models.benchmark_job import BenchmarkJob
from app.models.document import DocumentRecord

logger = logging.getLogger(__name__)
_STOP_REQUESTED = False


def _request_stop(signum: int, frame: object) -> None:
    """Request graceful shutdown after the current job reaches a safe boundary."""
    del signum, frame
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def _load_job_inputs(job_id: str) -> tuple[str, list[str], str] | None:
    """Read the source document reference and selected engines in a short transaction."""
    with SessionFactory() as session:
        job = session.get(BenchmarkJob, job_id)
        if job is None or job.status != "running":
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


async def _lease_heartbeat(job_id: str, lease_seconds: int) -> None:
    """Keep long-running jobs from being reclaimed by another worker."""
    interval = max(5.0, lease_seconds / 3)
    while True:
        await asyncio.sleep(interval)
        renewed = await asyncio.to_thread(_renew_lease, job_id, lease_seconds)
        if not renewed:
            return


def _serialize_result(result: object) -> dict[str, Any]:
    """Convert benchmark dataclasses into JSON-compatible result structures."""
    return asdict(result)


async def _execute_job(job_id: str) -> None:
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
        factory = create_default_ocr_factory()
        adapters = factory.create_many(engine_names)
        runner = OCRBenchmarkRunner(
            PDFPageRenderer(
                max_pages=settings.max_pdf_pages,
                max_page_dimension_pixels=int(settings.max_pdf_page_dimension_points * 200 / 72),
            ),
            BenchmarkConfig(
                engine_timeout_seconds=settings.ocr_engine_timeout_seconds,
                max_concurrent_engines=settings.ocr_max_concurrent_engines,
                max_total_rendered_image_bytes=settings.ocr_max_rendered_image_bytes,
            ),
        )
        heartbeat = asyncio.create_task(
            _lease_heartbeat(job_id, settings.ocr_worker_lease_seconds)
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
        raise
    except Exception as exc:
        logger.exception("Benchmark job %s failed", job_id)
        await asyncio.to_thread(
            _finish_job,
            job_id,
            "failed",
            error=f"Benchmark execution failed ({type(exc).__name__}).",
        )


def run_worker() -> None:
    """Poll and claim jobs until SIGINT or SIGTERM requests shutdown."""
    settings = get_settings()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    while not _STOP_REQUESTED:
        try:
            with SessionFactory() as session:
                job = BenchmarkJobRepository(session).claim_next(
                    settings.ocr_worker_lease_seconds
                )
                job_id = job.id if job is not None else None
                attempt_count = job.attempt_count if job is not None else 0
            if job_id is None:
                time.sleep(settings.ocr_worker_poll_seconds)
                continue
            if attempt_count > settings.ocr_worker_max_attempts:
                _finish_job(
                    job_id,
                    "failed",
                    error="Benchmark exceeded the maximum worker recovery attempts.",
                )
                continue
            asyncio.run(_execute_job(job_id))
        except Exception:
            logger.exception("Benchmark worker loop failed")
            time.sleep(settings.ocr_worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
