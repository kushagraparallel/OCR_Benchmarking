"""Typed, engine-independent OCR request and response models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OCRImage:
    """Encoded image and source-page identity passed to an OCR adapter."""

    image_bytes: bytes
    page_number: int

    def __post_init__(self) -> None:
        """Reject invalid page identities and empty image payloads early."""
        if self.page_number < 1:
            raise ValueError("page_number must be a positive, one-based page number.")
        if not self.image_bytes:
            raise ValueError("image_bytes must not be empty.")


@dataclass(frozen=True, slots=True)
class OCRBoundingBox:
    """Axis-aligned word bounds in pixels relative to the submitted image."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class OCRWord:
    """A recognized word with optional confidence and image-space bounds."""

    text: str
    bounding_box: OCRBoundingBox
    confidence: float | None


@dataclass(frozen=True, slots=True)
class OCRResult:
    """Normalized result returned by every OCR engine adapter."""

    engine_name: str
    engine_version: str
    page_number: int
    text: str
    words: tuple[OCRWord, ...]
    duration_ms: float
