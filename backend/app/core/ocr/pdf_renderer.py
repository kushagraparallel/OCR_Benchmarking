"""Bounded PDF-to-image rendering for downstream OCR adapters."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import fitz

from app.core.ocr.errors import OCRInputError

logger = logging.getLogger(__name__)

DEFAULT_RENDER_DPI = 200
DEFAULT_MAX_PAGES = 100
DEFAULT_MAX_PAGE_PIXELS = 40_000_000
DEFAULT_MAX_PAGE_DIMENSION_PIXELS = 10_000


@dataclass(frozen=True, slots=True)
class RenderedPDFPage:
    """PNG representation of one PDF page, with source identity and render settings."""

    page_number: int
    image_bytes: bytes
    width_pixels: int
    height_pixels: int
    dpi: int


class PDFPageRenderer:
    """Render PDF pages incrementally while enforcing resource limits."""

    def __init__(
        self,
        dpi: int = DEFAULT_RENDER_DPI,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_page_pixels: int = DEFAULT_MAX_PAGE_PIXELS,
        max_page_dimension_pixels: int = DEFAULT_MAX_PAGE_DIMENSION_PIXELS,
    ) -> None:
        if not 36 <= dpi <= 600:
            raise ValueError("dpi must be between 36 and 600.")
        if max_pages < 1:
            raise ValueError("max_pages must be a positive integer.")
        if max_page_pixels < 1:
            raise ValueError("max_page_pixels must be a positive integer.")
        if max_page_dimension_pixels < 1:
            raise ValueError("max_page_dimension_pixels must be a positive integer.")

        self._dpi = dpi
        self._max_pages = max_pages
        self._max_page_pixels = max_page_pixels
        self._max_page_dimension_pixels = max_page_dimension_pixels

    def render_pages(self, pdf_bytes: bytes) -> Iterator[RenderedPDFPage]:
        """Yield rendered pages in order without retaining every page image in memory."""
        if not pdf_bytes:
            raise OCRInputError("The supplied PDF is empty.")

        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except (fitz.FileDataError, ValueError, RuntimeError) as exc:
            raise OCRInputError("The supplied bytes are not a readable PDF.") from exc

        with document:
            if document.needs_pass:
                raise OCRInputError("Encrypted PDFs are not supported by the renderer.")
            if document.page_count < 1:
                raise OCRInputError("The PDF does not contain any pages.")
            if document.page_count > self._max_pages:
                raise OCRInputError(
                    f"The PDF contains {document.page_count} pages; "
                    f"the limit is {self._max_pages}."
                )

            scale = self._dpi / 72.0
            for page_index in range(document.page_count):
                page_number = page_index + 1
                try:
                    page = document.load_page(page_index)
                    page_width = page.rect.width
                    page_height = page.rect.height
                    width_pixels = int(page_width * scale + 0.5)
                    height_pixels = int(page_height * scale + 0.5)
                    self._validate_page_dimensions(
                        page_number=page_number,
                        width_pixels=width_pixels,
                        height_pixels=height_pixels,
                    )
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale),
                        colorspace=fitz.csRGB,
                        alpha=False,
                    )
                    image_bytes = pixmap.tobytes("png")
                except OCRInputError:
                    raise
                except (fitz.FitzError, ValueError, RuntimeError) as exc:
                    logger.exception("Failed to render PDF page %s", page_number)
                    raise OCRInputError(
                        f"PDF page {page_number} could not be rendered safely."
                    ) from exc

                yield RenderedPDFPage(
                    page_number=page_number,
                    image_bytes=image_bytes,
                    width_pixels=pixmap.width,
                    height_pixels=pixmap.height,
                    dpi=self._dpi,
                )

    def _validate_page_dimensions(
        self,
        page_number: int,
        width_pixels: int,
        height_pixels: int,
    ) -> None:
        """Reject page dimensions that could trigger excessive raster allocation."""
        if width_pixels < 1 or height_pixels < 1:
            raise OCRInputError(f"PDF page {page_number} has invalid dimensions.")
        if (
            width_pixels > self._max_page_dimension_pixels
            or height_pixels > self._max_page_dimension_pixels
        ):
            raise OCRInputError(
                f"PDF page {page_number} exceeds the maximum rendered dimension "
                f"of {self._max_page_dimension_pixels} pixels."
            )
        if width_pixels * height_pixels > self._max_page_pixels:
            raise OCRInputError(
                f"PDF page {page_number} exceeds the "
                f"{self._max_page_pixels}-pixel rendering limit."
            )
