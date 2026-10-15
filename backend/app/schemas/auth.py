"""Request and response schemas for authentication and session management."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegistrationRequest(BaseModel):
    """Validate a new account registration request."""
    email: EmailStr = Field(..., description="Email address used to sign in.")
    password: str = Field(..., min_length=12, max_length=128, description="Account password.")


class LoginRequest(BaseModel):
    """Validate an account login request."""
    email: EmailStr = Field(..., description="Registered email address.")
    password: str = Field(..., min_length=1, max_length=128, description="Account password.")


class UserResponse(BaseModel):
    """Public account details; never includes password hashes."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Short-lived access token returned after authentication."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds.")
    user: UserResponse


class SessionResponse(BaseModel):
    """A session summary safe to expose to its owner."""
    id: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    user_agent: str | None


class SessionListResponse(BaseModel):
    """List of sessions belonging to the authenticated user."""
    items: list[SessionResponse]


class MessageResponse(BaseModel):
    """A simple operation result message."""
    message: str
