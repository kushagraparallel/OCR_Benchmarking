"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

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
    document_storage_root: Path = Field(default=Path("./var/ocrlab/documents"), description="Private root directory for uploaded documents.")
    max_document_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=250 * 1024 * 1024, description="Maximum uploaded document size in bytes.")
    max_pdf_pages: int = Field(default=100, ge=1, le=1000, description="Maximum page count accepted per PDF.")
    max_pdf_page_dimension_points: float = Field(default=14400.0, gt=0, le=14400.0, description="Maximum width or height of a PDF page in points.")
    ocr_engine_timeout_seconds: float = Field(default=120.0, gt=0, le=3600, description="Per-engine per-page timeout.")
    ocr_max_concurrent_engines: int = Field(default=1, ge=1, le=4, description="Maximum concurrent engine inferences within one worker process.")
    ocr_max_rendered_image_bytes: int = Field(default=268435456, ge=1048576, le=2147483648, description="Maximum cumulative rendered PNG bytes per benchmark.")
    ocr_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=30, description="Database queue polling interval in seconds.")
    ocr_worker_lease_seconds: int = Field(default=300, ge=30, le=3600, description="Lease duration renewed while a benchmark is running.")
    ocr_worker_max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum recoveries after a worker loses a job lease.")
    ocr_max_concurrent_benchmark_jobs: int = Field(default=1, ge=1, le=32, description="Deployment-wide active benchmark job limit enforced through PostgreSQL worker slots.")
    ocr_enabled_engines: list[str] = Field(default=["tesseract"], description="Explicitly enabled OCR engine names.")
    ocr_easyocr_model_directory: Path | None = Field(default=None, description="Pre-provisioned EasyOCR model directory; required to enable EasyOCR.")
    ocr_paddle_detection_model_directory: Path | None = Field(default=None, description="Pre-provisioned PaddleOCR detection model directory.")
    ocr_paddle_recognition_model_directory: Path | None = Field(default=None, description="Pre-provisioned PaddleOCR recognition model directory.")
    ocr_paddle_classification_model_directory: Path | None = Field(default=None, description="Pre-provisioned PaddleOCR angle-classification model directory.")
    ocr_doctr_det_arch: str = Field(default="db_resnet50", description="docTR text-detection architecture name.")
    ocr_doctr_reco_arch: str = Field(default="crnn_vgg16_bn", description="docTR text-recognition architecture name.")
    ocr_doctr_cache_directory: Path | None = Field(default=None, description="Pre-provisioned docTR weights cache directory; required to enable docTR.")

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
