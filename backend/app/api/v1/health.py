"""Health-check endpoints for the versioned API."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Check API health")
def get_health() -> dict[str, str]:
    """Return a lightweight health response without checking external services."""
    return {"status": "ok"}
