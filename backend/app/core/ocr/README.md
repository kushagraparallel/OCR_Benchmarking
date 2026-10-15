# OCR Adapter Layer

## Purpose

The OCR domain provides one engine-independent contract so benchmark orchestration can run multiple engines without depending on their vendor-specific APIs. Each adapter accepts encoded image bytes and a one-based source page number, then returns normalized text, word-level confidence, pixel bounding boxes, engine identity/version, and elapsed milliseconds.

## Current implementation

- `base.py`: abstract `OCRAdapter` contract.
- `schemas.py`: immutable `OCRImage`, `OCRBoundingBox`, `OCRWord`, and `OCRResult` data classes.
- `errors.py`: stable domain errors for missing dependencies, invalid input, and engine failures.
- `tesseract.py`: Tesseract adapter, using `pytesseract.image_to_data` to return text and word-level geometry.
- `easyocr.py`: optional EasyOCR adapter with lazy dependency/model initialization and shared normalized results.
- `paddleocr.py`: optional PaddleOCR 2.x adapter with explicit local model paths, lazy initialization, and normalized detection output.
- `doctr.py`: optional docTR adapter with an explicit predictor factory, lazy model initialization, and normalized document export.
- `pdf_renderer.py`: bounded, incremental PDF page renderer using PyMuPDF; yields one PNG page at a time.

## Optional EasyOCR setup

EasyOCR is intentionally excluded from the default backend dependency set because it brings PyTorch and native computer-vision dependencies. To install it in a dedicated environment, run `pip install -r requirements-ocr-easyocr.txt` from the `backend/` directory. This optional requirements file includes the base backend requirements and pins EasyOCR to `1.7.2`; EasyOCR's transitive packages are resolved by pip and should be locked in a deployment-specific lock file before production use.

`EasyOCRAdapter` is lazy: constructing it does not import EasyOCR or load models. The first recognition call initializes one shared reader, then reuses it for later pages. `download_enabled` defaults to `False`, so required model files must be provisioned in advance; this avoids model downloads triggered by a request. CPU mode is the default. Enable GPU only after validating the installed PyTorch/CUDA combination and memory budget. A lock protects model initialization and inference because reader thread-safety should not be assumed.

EasyOCR's detection confidence (0–1) is converted to the common 0–100 scale. Polygon coordinates are normalized to conservative pixel-aligned rectangular bounds. This makes confidence fields comparable in representation, but not necessarily statistically comparable across engines; benchmark reports should identify the engine and avoid treating confidence as ground-truth accuracy.

## Optional PaddleOCR setup

PaddleOCR is excluded from the base requirements because it adds a large OCR/runtime dependency stack. Install it in a dedicated worker environment using `pip install -r requirements-ocr-paddleocr.txt` from the `backend/` directory. This optional file pins PaddleOCR 2.9.1 and PaddlePaddle 2.6.2 because the adapter targets the PaddleOCR 2.x API; use a compatible Python/platform combination and validate the dependency set before deployment.

`PaddleOCRAdapter` requires existing local detection and recognition model directories, plus a classification model directory when angle classification is enabled. It does not allow implicit model-directory defaults, which avoids a request silently downloading model weights. Provision model files as part of environment setup and verify that their format matches the pinned runtime. Engine initialization is lazy and reused. Initialization and inference are protected by a lock rather than assuming the engine is thread-safe. CPU is the default; GPU mode requires a matching PaddlePaddle/CUDA build and an explicit memory/concurrency budget.

The adapter converts PaddleOCR polygons to conservative pixel-aligned rectangles and maps confidence from 0–1 to the shared 0–100 representation. Empty-page output is valid. Malformed results and non-finite coordinates raise a domain execution error. Confidence scales are normalized in representation only and must not be treated as comparable accuracy estimates across engines.

## Optional docTR setup

docTR is excluded from the default backend requirements because its model backend adds a substantial machine-learning runtime. Install it in a dedicated worker environment with `pip install -r requirements-ocr-doctr.txt` from the `backend/` directory. The optional file pins `python-doctr[torch]==0.10.0`; validate the resolved PyTorch build for the target operating system and hardware before deployment.

`DocTRAdapter` takes a required `predictor_factory` instead of silently selecting pretrained models. The application should configure the factory with approved architectures and locally provisioned weights, for example by constructing a docTR OCR predictor with pretrained downloads disabled. The factory is called lazily once and the predictor is reused. This keeps model policy explicit and prevents request-time model downloads. CPU is the safe default until GPU compatibility and concurrency limits are verified.

docTR exports relative word geometry and page dimensions. The adapter scales relative coordinates into pixel bounds, preserves export reading order, and converts confidence to the shared 0–100 representation. This is a representation convention, not cross-engine confidence calibration. The adapter currently expects one submitted image and normalizes the first exported page.

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


`backend/tests/test_ocr_tesseract.py` uses deterministic in-memory PNGs and mocks the Tesseract subprocess boundary. The unit tests do not require a native Tesseract installation and cover normalized text/words, invalid image bytes, pixel limits, timeout conversion, page numbering, and configuration validation. `backend/tests/test_ocr_easyocr.py` tests the optional adapter's lazy initialization, reader reuse, confidence/coordinate normalization, malformed output, and input validation without downloading EasyOCR models. `backend/tests/test_ocr_paddleocr.py` tests lazy initialization, required model paths, output normalization, empty results, non-finite coordinates, and configuration without importing PaddleOCR or downloading model weights. `backend/tests/test_ocr_doctr.py` tests predictor reuse, exported geometry normalization, empty results, malformed output, invalid images, and the recognition result contract using mocks.

## Remaining

- Add native Tesseract smoke tests in a CI job or documented local validation environment.
- Validate EasyOCR against a real sample corpus with provisioned model files and benchmark its RAM/latency footprint.
- Validate PaddleOCR against real documents using pre-provisioned model files; record runtime version, accuracy, cold-start time, latency, and memory.
- Validate docTR on real documents with a locally configured predictor and provisioned weights; record architecture, cold-start time, inference latency, and memory.
- Add a registry/factory and benchmark orchestration only after adapter contracts are stable.
- Record adapter configuration and engine/model versions with each benchmark result.
- Validate language-specific behavior and reading-order assumptions against a representative document corpus.
