"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with explicit security and database configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    app_name: str = Field(default="OCRLab API", description="Application display name.")
    app_version: str = Field(default="0.1.0", description="Application version.")
    app_environment: str = Field(default="development", description="Deployment environment.")
    api_v1_prefix: str = Field(default="/api/v1", description="Prefix used for versioned API endpoints.")
    cors_origins: list[str] = Field(default=["http://localhost:5173"], description="Explicit frontend origins permitted to access the API.")
    database_url: str = Field(default="postgresql+psycopg://ocrlab:ocrlab@localhost:5432/ocrlab", description="SQLAlchemy database URL.")
    jwt_secret_key: str = Field(default="development-only-change-this-secret-before-deploying", min_length=32, description="Signing secret for access JWTs; override with JWT_SECRET_KEY.")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    jwt_issuer: str = Field(default="ocrlab-api", description="Expected JWT issuer.")
    jwt_audience: str = Field(default="ocrlab-client", description="Expected JWT audience.")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60, description="Access token lifetime in minutes.")
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30, description="Refresh token/session lifetime in days.")
    refresh_cookie_name: str = Field(default="ocrlab_refresh", description="Name of the HttpOnly refresh-token cookie.")

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Reject development-only signing secrets in production deployments."""
        if self.app_environment.casefold() == "production":
            if self.jwt_secret_key == "development-only-change-this-secret-before-deploying":
                raise ValueError("JWT_SECRET_KEY must be explicitly configured in production.")
            if len(self.jwt_secret_key) < 48:
                raise ValueError("JWT_SECRET_KEY must contain at least 48 characters in production.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
