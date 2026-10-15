"""HTTP endpoints for account authentication and current-user operations."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth.dependencies import CurrentUser, DatabaseSession
from app.core.auth.errors import EmailAlreadyRegisteredError, InvalidCredentialsError, InvalidRefreshTokenError
from app.core.auth.security import decode_access_token
from app.core.auth.service import AuthenticationService
from app.db.repositories.auth_repository import AuthRepository
from app.models import User
from app.schemas.auth import LoginRequest, MessageResponse, RegistrationRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the refresh secret in a protected, HTTP-only browser cookie."""
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.app_environment.casefold() == "production",
        samesite="strict",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh cookie using the same path and security attributes."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}/auth",
        httponly=True,
        secure=settings.app_environment.casefold() == "production",
        samesite="strict",
    )


def _token_response(user: User, access_token: str, lifetime: int) -> TokenResponse:
    """Build the public token response without exposing session or refresh secrets."""
    return TokenResponse(
        access_token=access_token,
        expires_in=lifetime,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_account(payload: RegistrationRequest, database_session: DatabaseSession) -> UserResponse:
    """Register an account; duplicate email addresses return a conflict response."""
    try:
        user = AuthenticationService(database_session).register(str(payload.email), payload.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from None
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login_account(payload: LoginRequest, request: Request, response: Response, database_session: DatabaseSession) -> TokenResponse:
    """Authenticate an account and set its refresh token in an HTTP-only cookie."""
    try:
        user, access_token, refresh_token, lifetime = AuthenticationService(database_session).login(
            str(payload.email), payload.password, request.headers.get("user-agent")
        )
    except InvalidCredentialsError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.", headers={"WWW-Authenticate": "Bearer"}) from None
    _set_refresh_cookie(response, refresh_token)
    return _token_response(user, access_token, lifetime)


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(request: Request, response: Response, database_session: DatabaseSession) -> TokenResponse:
    """Rotate the refresh cookie and issue a new access token."""
    settings = get_settings()
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required.")
    try:
        user, access_token, new_refresh_token, lifetime, _ = AuthenticationService(database_session).refresh(raw_refresh_token)
    except InvalidRefreshTokenError:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid or expired.") from None
    _set_refresh_cookie(response, new_refresh_token)
    return _token_response(user, access_token, lifetime)


@router.post("/logout", response_model=MessageResponse)
def logout_account(request: Request, response: Response, database_session: DatabaseSession) -> MessageResponse:
    """Revoke the browser session represented by its refresh cookie, if present."""
    settings = get_settings()
    AuthenticationService(database_session).logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out.")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all_accounts(user: CurrentUser, response: Response, database_session: DatabaseSession) -> MessageResponse:
    """Revoke all sessions for the authenticated user."""
    AuthenticationService(database_session).logout_all(user.id)
    _clear_refresh_cookie(response)
    return MessageResponse(message="All sessions have been revoked.")


@router.get("/me", response_model=UserResponse)
def get_current_account(user: CurrentUser) -> UserResponse:
    """Return the authenticated user's public profile."""
    return UserResponse.model_validate(user)
