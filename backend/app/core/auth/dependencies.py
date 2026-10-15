"""FastAPI dependencies for resolving authenticated users."""

from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth.security import decode_access_token
from app.db.database import get_database_session
from app.db.repositories.auth_repository import AuthRepository
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_database_session)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    database_session: DatabaseSession,
) -> User:
    """Validate the access token and require an active user and session."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
        session_id = str(claims["sid"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized from None

    repository = AuthRepository(database_session)
    user = repository.get_user_by_id(user_id)
    user_session = repository.get_session(session_id)
    now = datetime.now(timezone.utc)
    if user_session is not None and user_session.expires_at.tzinfo is None:
        session_expiry = user_session.expires_at.replace(tzinfo=timezone.utc)
    elif user_session is not None:
        session_expiry = user_session.expires_at.astimezone(timezone.utc)
    else:
        session_expiry = now
    if (
        user is None
        or not user.is_active
        or user_session is None
        or user_session.user_id != user.id
        or user_session.revoked_at is not None
        or session_expiry <= now
    ):
        raise unauthorized
    return user
