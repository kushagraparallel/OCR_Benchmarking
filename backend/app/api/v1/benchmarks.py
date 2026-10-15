"""Authenticated API endpoints for submitting and tracking OCR benchmarks."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.auth.dependencies import CurrentUser, DatabaseSession
from app.core.benchmarks.service import (
    BenchmarkJobNotFoundError,
    BenchmarkJobService,
    InvalidBenchmarkStateError,
)
from app.core.documents.errors import DocumentNotFoundError
from app.core.ocr.registry import create_default_ocr_factory
from app.schemas.benchmarks import (
    BenchmarkJobCreateRequest,
    BenchmarkJobListResponse,
    BenchmarkJobResponse,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


def _service(database_session: DatabaseSession) -> BenchmarkJobService:
    """Build a request-scoped job service with engines supported by this API."""
    return BenchmarkJobService(database_session, create_default_ocr_factory())


@router.post("", response_model=BenchmarkJobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_benchmark(
    payload: BenchmarkJobCreateRequest,
    user: CurrentUser,
    database_session: DatabaseSession,
) -> BenchmarkJobResponse:
    """Queue a benchmark for an uploaded PDF owned by the authenticated user."""
    try:
        job = _service(database_session).submit(user.id, payload.document_id, payload.engine_names)
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.") from None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return BenchmarkJobResponse.model_validate(job)


@router.get("", response_model=BenchmarkJobListResponse)
def list_benchmarks(
    user: CurrentUser,
    database_session: DatabaseSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BenchmarkJobListResponse:
    """List only the authenticated user's benchmark jobs."""
    jobs = _service(database_session).list_owned(user.id, limit, offset)
    return BenchmarkJobListResponse(
        items=[BenchmarkJobResponse.model_validate(job) for job in jobs],
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=BenchmarkJobResponse)
def get_benchmark(
    job_id: UUID,
    user: CurrentUser,
    database_session: DatabaseSession,
) -> BenchmarkJobResponse:
    """Return persisted status and results for an owned benchmark job."""
    try:
        job = _service(database_session).get_owned(str(job_id), user.id)
    except BenchmarkJobNotFoundError:
        raise HTTPException(status_code=404, detail="Benchmark job not found.") from None
    return BenchmarkJobResponse.model_validate(job)


@router.delete("/{job_id}", response_model=BenchmarkJobResponse)
def cancel_benchmark(
    job_id: UUID,
    user: CurrentUser,
    database_session: DatabaseSession,
) -> BenchmarkJobResponse:
    """Cancel queued work or request cancellation at the next page boundary."""
    try:
        job = _service(database_session).cancel_owned(str(job_id), user.id)
    except BenchmarkJobNotFoundError:
        raise HTTPException(status_code=404, detail="Benchmark job not found.") from None
    except InvalidBenchmarkStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return BenchmarkJobResponse.model_validate(job)
