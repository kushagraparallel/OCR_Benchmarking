"""Abstract contract shared by all OCR engine implementations."""

from abc import ABC, abstractmethod

from app.core.ocr.schemas import OCRImage, OCRResult


class OCRAdapter(ABC):
    """Recognize text from one encoded page image using a specific OCR engine."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return a stable, human-readable engine identifier."""

    @abstractmethod
    def get_version(self) -> str:
        """Return the installed engine version or raise a dependency error."""

    @abstractmethod
    def recognize(self, image: OCRImage) -> OCRResult:
        """Recognize one page and return normalized text, words, and timing."""
