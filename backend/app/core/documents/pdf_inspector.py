"""Validate PDF structure and extract bounded metadata using PyMuPDF."""

from dataclasses import dataclass
from pathlib import Path

import fitz

from app.core.documents.errors import InvalidPdfError, PdfLimitExceededError


@dataclass(frozen=True, slots=True)
class PdfInspection:
    """Validated metadata required to persist an uploaded PDF."""

    page_count: int
    title: str | None
    author: str | None


class PdfInspector:
    """Validate that a staged file is a readable PDF within resource limits."""

    def __init__(self, max_pages: int, max_page_dimension_points: float) -> None:
        self._max_pages = max_pages
        self._max_page_dimension_points = max_page_dimension_points

    def inspect(self, file_path: Path) -> PdfInspection:
        """Reject malformed, encrypted, empty, or resource-excessive PDFs."""
        try:
            with file_path.open("rb") as pdf_file:
                header = pdf_file.read(1024)
            if b"%PDF-" not in header:
                raise InvalidPdfError("The uploaded file is not a PDF.")

            with fitz.open(file_path) as pdf_document:
                if pdf_document.is_encrypted:
                    raise InvalidPdfError("Password-protected PDFs are not supported.")
                page_count = pdf_document.page_count
                if page_count < 1:
                    raise InvalidPdfError("The PDF contains no pages.")
                if page_count > self._max_pages:
                    raise PdfLimitExceededError(
                        f"The PDF exceeds the maximum of {self._max_pages} pages."
                    )

                for page_number in range(page_count):
                    page_rectangle = pdf_document.load_page(page_number).rect
                    if (
                        page_rectangle.width <= 0
                        or page_rectangle.height <= 0
                        or page_rectangle.width > self._max_page_dimension_points
                        or page_rectangle.height > self._max_page_dimension_points
                    ):
                        raise PdfLimitExceededError(
                            "A PDF page has invalid or excessive dimensions."
                        )

                metadata = pdf_document.metadata or {}
                return PdfInspection(
                    page_count=page_count,
                    title=self._clean_metadata(metadata.get("title"), 512),
                    author=self._clean_metadata(metadata.get("author"), 255),
                )
        except (InvalidPdfError, PdfLimitExceededError):
            raise
        except Exception as exc:
            # Parser errors vary by PyMuPDF version; do not leak parser details to clients.
            raise InvalidPdfError("The PDF is malformed or cannot be read.") from exc

    @staticmethod
    def _clean_metadata(value: object, max_length: int) -> str | None:
        """Discard non-string and blank metadata and bound database field length."""
        if not isinstance(value, str):
            return None
        cleaned_value = "".join(character for character in value.strip() if character.isprintable())
        return cleaned_value[:max_length] or None
