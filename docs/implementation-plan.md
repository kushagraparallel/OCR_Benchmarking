# OCRLab Implementation Plan

This file is the source of truth for implemented scope, outstanding work, and phase exit criteria. Update it in the same change that materially changes implementation status.

## Status summary

| Phase | Status | Notes |
|---|---|---|
| 1. Repository and API foundation | Implemented; CI result pending verification | FastAPI app factory, typed settings, versioned health endpoint, initial tests and CI workflow |
| 2. Persistence foundation | Foundation implemented; schema work remaining | SQLAlchemy engine/session/base and Alembic setup are present; no domain tables or database integration endpoint yet |
| 3. Authentication and sessions | Not started | Password hashing, JWT, refresh-token rotation and revocation |
| 4. PDF ingestion | Not started | PDF validation, limits, private storage and metadata |
| 5. OCR adapters | Not started | Tesseract, EasyOCR, PaddleOCR and docTR |
| 6. Benchmark execution and evaluation | Not started | Worker queue, run lifecycle, metrics, CER/WER |
| 7. Frontend and reporting | Not started | React UI, charts and exports |
| 8. Hardening and deployment | Not started | Security, integration/performance tests, containers and operational docs |

## Phase 1 — Repository and API foundation

Implemented:
- Repository overview and phased plan.
- Environment-based Pydantic settings.
- FastAPI application factory and /api/v1/health.
- Initial API tests.
- Pinned initial backend dependencies.
- GitHub Actions workflow for Python compilation and tests.

Remaining:
- Confirm a successful GitHub Actions run; do not infer passing checks from the workflow file alone.
- Add linting/type-checking after the baseline CI is confirmed and tool versions are agreed.

## Phase 2 — Persistence foundation

Implemented:
- SQLAlchemy 2.x engine factory with connection pre-ping.
- One reusable application engine and session factory.
- Request-scoped session dependency with rollback on propagated exceptions.
- Shared declarative base.
- Alembic configuration, environment, and migration template.
- In-memory SQLite unit tests for engine and session behavior.
- Database setup and migration documentation.

Remaining:
- Add PostgreSQL service configuration for local development and CI integration tests.
- Introduce domain models and migrations in small increments, beginning with users and sessions during authentication.
- Add repository interfaces and persistence tests alongside each domain.
- Add a deliberate database readiness check when a real database-dependent endpoint is introduced.
- Test migrations against PostgreSQL before merging schema changes.

## Phase 3 — Authentication and sessions

- Registration/login and safe password hashing (Argon2id).
- Short-lived access JWTs, opaque refresh tokens stored hashed, rotation and reuse detection.
- Revocable sessions, ownership checks, and security tests.
- Secure cookie/CSRF design appropriate to the frontend deployment.

## Phase 4 — PDF ingestion

- Validate actual PDF content, file size, page count and rendered page dimensions.
- Generate safe storage identifiers; keep uploads outside the public web root.
- Extract PDF metadata and distinguish digital/scanned/mixed pages where feasible.
- Add retention and deletion behavior.

## Phase 5 — OCR adapters

- Define a normalized adapter contract.
- Add Tesseract, EasyOCR, PaddleOCR, and docTR as independent adapters.
- Pin and document system dependencies/model versions.
- Test normalized outputs and isolate engine-specific failures.

## Phase 6 — Benchmark execution and evaluation

- Add queue/worker execution and explicit benchmark state transitions.
- Run engines on identical page images and record configuration/version information.
- Capture timing, throughput and resource metrics.
- Calculate CER/WER only when a reference transcription is supplied; never present word count as accuracy.

## Phase 7 — Frontend and reporting

- React/TypeScript app with authentication, upload, benchmark configuration, history and results.
- Charts for latency, throughput, memory, and ground-truth metrics.
- CSV/PDF exports and clear labeling of unavailable metrics.

## Phase 8 — Hardening and deployment

- Security, integration and representative-corpus tests.
- Docker Compose for frontend, API, PostgreSQL, Redis and workers when those components exist.
- Operational runbooks, retention policy, monitoring and reproducible environment setup.

## Validation policy

For every implementation phase:
1. Run Python compilation and focused tests.
2. Run the full backend test suite.
3. Confirm CI status before describing checks as passing.
4. Test database migrations against PostgreSQL when schema changes are introduced.
5. Report unexecuted checks and external prerequisites explicitly.

Dependency installation, database connectivity, OCR model downloads, and source compilation are distinct checks and must not be conflated.
