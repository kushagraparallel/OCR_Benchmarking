"""Validated API schemas for benchmark job submission and status."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkJobCreateRequest(BaseModel):
    """Requested engines for a benchmark against an already uploaded PDF."""

    document_id: str = Field(min_length=36, max_length=36)
    engine_names: list[str] = Field(min_length=1, max_length=4)

    @field_validator("engine_names")
    @classmethod
    def validate_engine_names(cls, names: list[str]) -> list[str]:
        """Normalize engine names and reject empty or duplicate selections."""
        normalized = [name.strip().casefold() for name in names]
        if any(not name for name in normalized):
            raise ValueError("Engine names must not be empty.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate engine names are not allowed.")
        return normalized


class BenchmarkJobResponse(BaseModel):
    """Public status and result representation without internal lease data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    engine_names: list[str]
    status: Literal[
        "queued", "running", "cancellation_requested", "cancelled",
        "completed", "partial", "failed",
    ]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempt_count: int


class BenchmarkJobListResponse(BaseModel):
    """Paginated job history for the authenticated account."""

    items: list[BenchmarkJobResponse]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
