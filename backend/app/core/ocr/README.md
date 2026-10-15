# OCR Adapter Layer

## Purpose

The OCR domain provides one engine-independent contract so benchmark orchestration can run multiple engines without depending on their vendor-specific APIs. Each adapter accepts encoded image bytes and a one-based source page number, then returns normalized text, word-level confidence, pixel bounding boxes, engine identity/version, and elapsed milliseconds.

## Current implementation

- `base.py`: abstract `OCRAdapter` contract.
- `schemas.py`: immutable `OCRImage`, `OCRBoundingBox`, `OCRWord`, and `OCRResult` data classes.
- `errors.py`: stable domain errors for missing dependencies, invalid input, and engine failures.
- `tesseract.py`: first concrete adapter, using `pytesseract.image_to_data` to return both text and word-level geometry.

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

## Tests

GitHub Actions passed on commit `b2bd38c5e809f990f4dbb444904964191a2ee36d`: Python compilation, offline Alembic SQL generation, and 27 backend tests passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38728100165.


`backend/tests/test_ocr_tesseract.py` uses deterministic in-memory PNGs and mocks the Tesseract subprocess boundary. The unit tests do not require a native Tesseract installation and cover normalized text/words, invalid image bytes, pixel limits, timeout conversion, page numbering, and configuration validation.

## Remaining

- Add the PDF page renderer with explicit DPI and pixel/dimension limits.
- Add native Tesseract smoke tests in a CI job or documented local validation environment.
- Add EasyOCR, PaddleOCR, and docTR adapters using the same contract.
- Add a registry/factory and benchmark orchestration only after adapter contracts are stable.
- Record adapter configuration and engine/model versions with each benchmark result.
- Validate language-specific behavior and reading-order assumptions against a representative document corpus.
