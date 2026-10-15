# OCR Adapter Layer

## Purpose

The OCR domain provides one engine-independent contract so benchmark orchestration can run multiple engines without depending on their vendor-specific APIs. Each adapter accepts encoded image bytes and a one-based source page number, then returns normalized text, word-level confidence, pixel bounding boxes, engine identity/version, and elapsed milliseconds.

## Current implementation

- `base.py`: abstract `OCRAdapter` contract.
- `schemas.py`: immutable `OCRImage`, `OCRBoundingBox`, `OCRWord`, and `OCRResult` data classes.
- `errors.py`: stable domain errors for missing dependencies, invalid input, and engine failures.
- `tesseract.py`: Tesseract adapter, using `pytesseract.image_to_data` to return text and word-level geometry.
- `pdf_renderer.py`: bounded, incremental PDF page renderer using PyMuPDF; yields one PNG page at a time.

## Tesseract system dependency

Python dependencies are pinned in `backend/requirements.txt`, but the Python package does not install the native Tesseract executable or its language data. Install Tesseract OCR separately and ensure the executable is available on `PATH`. On Windows, pass the executable path through the adapter's `tesseract_cmd` constructor argument when it is not on `PATH`. English is the default language; additional languages require the corresponding Tesseract trained-data files.

## Resource and error behavior

- The adapter decodes image bytes using Pillow and converts images to RGB.
- Images above the configurable pixel limit are rejected before calling Tesseract.
- Recognition has a configurable subprocess timeout (30 seconds by default).
- Missing native runtime and recognition failures raise domain-specific errors instead of returning fake/empty success results.
- Empty recognition output is valid when the engine successfully processes a blank page.
- Confidence is normalized to the 0–100 range; Tesseract's negative sentinel values become `None`.
- Bounding boxes use pixel coordinates relative to the exact submitted image. Page coordinates or PDF points are not implied.
- Recognition timing measures the OCR call, excluding image decoding and version lookup.

## PDF page rendering

`PDFPageRenderer` accepts PDF bytes and yields `RenderedPDFPage` objects in source-page order. Each result includes one-based page number, PNG bytes, rendered dimensions, and configured DPI. Defaults are 200 DPI, 100 pages, 40 million pixels per page, and 10,000 pixels per dimension. It rejects empty/malformed/encrypted PDFs, empty documents, excessive page counts, and pages that exceed raster limits before allocating the page pixmap. Configure the renderer explicitly for the expected workload; raising DPI increases memory and processing cost rapidly. Rendering is synchronous CPU work and must be run in a worker or offloaded from the FastAPI event loop.

Example:

```python
renderer = PDFPageRenderer(dpi=200)
for rendered_page in renderer.render_pages(pdf_bytes):
    ocr_image = OCRImage(
        image_bytes=rendered_page.image_bytes,
        page_number=rendered_page.page_number,
    )
    result = tesseract_adapter.recognize(ocr_image)
```

The renderer intentionally does not run OCR, persist files, or own benchmark lifecycle. Those responsibilities belong to orchestration services.

## Tests

GitHub Actions passed on commit `b2bd38c5e809f990f4dbb444904964191a2ee36d`: Python compilation, offline Alembic SQL generation, and 27 backend tests passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38728100165.


`backend/tests/test_ocr_tesseract.py` uses deterministic in-memory PNGs and mocks the Tesseract subprocess boundary. The unit tests do not require a native Tesseract installation and cover normalized text/words, invalid image bytes, pixel limits, timeout conversion, page numbering, and configuration validation.

## Remaining

- Add a PDF-to-PNG renderer with configurable DPI (36–600), maximum page count, maximum rendered dimension, and maximum pixels per page. It yields pages incrementally so the caller need not retain every page image in memory.
- Add native Tesseract smoke tests in a CI job or documented local validation environment.
- Add EasyOCR, PaddleOCR, and docTR adapters using the same contract.
- Add a registry/factory and benchmark orchestration only after adapter contracts are stable.
- Record adapter configuration and engine/model versions with each benchmark result.
- Validate language-specific behavior and reading-order assumptions against a representative document corpus.
