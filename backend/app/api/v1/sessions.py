"""Endpoints for listing and revoking the current user's sessions."""

from fastapi import APIRouter, HTTPException, status

from app.core.auth.dependencies import CurrentUser, DatabaseSession
from app.core.auth.errors import SessionNotFoundError
from app.core.auth.service import AuthenticationService
from app.schemas.auth import MessageResponse, SessionListResponse, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
def list_user_sessions(user: CurrentUser, database_session: DatabaseSession) -> SessionListResponse:
    """List sessions owned by the authenticated user without exposing token secrets."""
    sessions = AuthenticationService(database_session).list_sessions(user.id)
    return SessionListResponse(items=[
        SessionResponse(
            id=item.id,
            created_at=item.created_at,
            expires_at=item.expires_at,
            last_used_at=item.last_used_at,
            user_agent=item.user_agent,
            is_current=False,
        )
        for item in sessions
    ])


@router.delete("/{session_id}", response_model=MessageResponse)
def revoke_user_session(session_id: str, user: CurrentUser, database_session: DatabaseSession) -> MessageResponse:
    """Revoke a session only if it belongs to the authenticated user."""
    try:
        AuthenticationService(database_session).revoke_owned_session(user.id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.") from None
    return MessageResponse(message="Session revoked.")
