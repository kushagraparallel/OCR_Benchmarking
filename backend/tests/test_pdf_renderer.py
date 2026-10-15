"""Unit tests for bounded PDF page rendering."""

import fitz
import pytest

from app.core.ocr.errors import OCRInputError
from app.core.ocr.pdf_renderer import PDFPageRenderer


def create_pdf_bytes(page_count: int = 2, width: float = 612, height: float = 792) -> bytes:
    """Build a small PDF fixture in memory without external test files."""
    document = fitz.open()
    for _ in range(page_count):
        document.new_page(width=width, height=height)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_render_pages_yields_png_pages_in_order() -> None:
    """Each rendered page should preserve source numbering and configured DPI."""
    renderer = PDFPageRenderer(dpi=144)
    pages = list(renderer.render_pages(create_pdf_bytes()))

    assert len(pages) == 2
    assert [page.page_number for page in pages] == [1, 2]
    assert all(page.image_bytes.startswith(b"\x89PNG\r\n\x1a\n") for page in pages)
    assert all(page.dpi == 144 for page in pages)
    assert all(page.width_pixels > 0 and page.height_pixels > 0 for page in pages)


def test_render_pages_rejects_empty_and_malformed_pdf() -> None:
    """Invalid input should fail with the OCR domain's input error."""
    renderer = PDFPageRenderer()
    with pytest.raises(OCRInputError, match="empty"):
        list(renderer.render_pages(b""))
    with pytest.raises(OCRInputError, match="not a readable PDF"):
        list(renderer.render_pages(b"not a pdf"))


def test_render_pages_rejects_excessive_page_count() -> None:
    """The page count is checked before allocating page images."""
    renderer = PDFPageRenderer(max_pages=1)
    with pytest.raises(OCRInputError, match="limit is 1"):
        list(renderer.render_pages(create_pdf_bytes(page_count=2)))


def test_render_pages_rejects_excessive_pixel_count_before_rendering() -> None:
    """Large raster allocations should be rejected before get_pixmap is called."""
    renderer = PDFPageRenderer(dpi=300, max_page_pixels=100_000)
    with pytest.raises(OCRInputError, match="rendering limit"):
        list(renderer.render_pages(create_pdf_bytes(page_count=1)))


def test_render_pages_rejects_excessive_single_dimension() -> None:
    """Extremely wide or tall pages should be rejected independently of total area."""
    renderer = PDFPageRenderer(
        dpi=72,
        max_page_pixels=10_000_000,
        max_page_dimension_pixels=500,
    )
    with pytest.raises(OCRInputError, match="maximum rendered dimension"):
        list(renderer.render_pages(create_pdf_bytes(page_count=1, width=600, height=100)))


def test_renderer_rejects_invalid_configuration() -> None:
    """Unsafe or nonsensical render settings should fail at construction."""
    with pytest.raises(ValueError, match="dpi"):
        PDFPageRenderer(dpi=10)
    with pytest.raises(ValueError, match="max_pages"):
        PDFPageRenderer(max_pages=0)
