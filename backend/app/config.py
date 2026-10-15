"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with safe development defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="OCRLab API", description="Application display name.")
    app_version: str = Field(default="0.1.0", description="Application version.")
    app_environment: str = Field(
        default="development",
        description="Deployment environment, such as development or production.",
    )
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="Prefix used for versioned API endpoints.",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173"],
        description="Explicit frontend origins permitted to access the API.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
