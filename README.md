# OCRLab

OCRLab is a modular OCR benchmarking platform for comparing locally executable OCR engines on the same PDF inputs.

## Initial scope

- Secure PDF ingestion and document metadata
- Independent OCR adapters for Tesseract, EasyOCR, PaddleOCR, and docTR
- Reproducible performance benchmarking
- Ground-truth-based CER/WER evaluation
- Comparison dashboards and report exports
- JWT authentication and revocable user sessions

RAG and intelligent OCR routing are explicitly out of scope for the initial release.

## Architecture

The repository uses separate `frontend/` and `backend/` applications. The backend follows a layered structure: thin API routers call domain services, which use repositories for database access. OCR execution runs in background workers rather than in API request handlers.

## Development status

The repository is being implemented in small, verifiable phases. See `docs/implementation-plan.md` for milestones and validation commands.

## Running locally

1. Backend: follow `backend/README.md` (PostgreSQL, migrations, `uvicorn`, and a worker process via `python -m app.workers.benchmark_worker`).
2. Frontend: follow `frontend/README.md` (`npm install && npm run dev`), served at `http://localhost:5173` by default, matching the backend's default CORS configuration.

## Security

Never commit `.env` files, production secrets, uploaded documents, model weights, or generated benchmark output. Copy `backend/.env.example` to a local environment file and configure development-only credentials before running the application.
