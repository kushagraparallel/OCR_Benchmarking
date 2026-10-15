# OCRLab Implementation Plan

This document is the source of truth for implemented scope, outstanding work, and validation criteria. Update it whenever implementation status changes.

## Status summary

| Phase | Status | Notes |
|---|---|---|
| 1. Repository and API foundation | Implemented; CI must be verified | FastAPI app factory, typed settings, versioned health endpoint, initial tests and CI workflow |
| 2. Persistence foundation | Implemented foundation; PostgreSQL validation pending | SQLAlchemy engine/session/base, repositories, Alembic and initial authentication schema migration |
| 3. Authentication and sessions | Implemented; CI and PostgreSQL concurrency validation pending | Argon2id, JWT access tokens, hashed rotating refresh tokens, revocation and session endpoints |
| 4. PDF ingestion | Not started | PDF validation, limits, private storage and metadata |
| 5. OCR adapters | Not started | Tesseract, EasyOCR, PaddleOCR and docTR |
| 6. Benchmark execution and evaluation | Not started | Worker queue, run lifecycle, metrics, CER/WER |
| 7. Frontend and reporting | Not started | React UI, charts and exports |
| 8. Hardening and deployment | Partial foundations only | CI and security design docs exist; production hardening and deployment remain |

## Phase 1 — Repository and API foundation

Implemented:
- Repository overview and phased plan.
- Environment-based Pydantic settings.
- FastAPI application factory and /api/v1/health.
- Initial API tests and pinned dependencies.
- GitHub Actions workflow for Python compilation and pytest.

Remaining:
- Confirm successful GitHub Actions checks.
- Add linting and type checking with pinned tool versions.
- Add request IDs and consistent structured error responses in a later hardening pass.

## Phase 2 — Persistence foundation

Implemented:
- SQLAlchemy 2.x engine factory with connection pre-ping.
- Shared application engine and session factory.
- Request-scoped session dependency with rollback on propagated exceptions.
- Shared declarative base and repository layer.
- Alembic configuration/environment/template.
- Initial migration creating users, user_sessions and refresh_tokens.
- SQLite unit-test support.

Remaining:
- Verify migration upgrade/downgrade against PostgreSQL.
- Add PostgreSQL service-backed CI integration tests.
- Add explicit database readiness checks when application startup/operations require database availability.
- Review schema diffs and migration naming on each schema change.

## Phase 3 — Authentication and sessions

Implemented:
- Registration with email normalization and duplicate-email conflict response.
- Argon2id password hashing and generic invalid-credential responses.
- Short-lived JWT access tokens with issuer, audience, expiry, token ID and session ID claims.
- Opaque high-entropy refresh tokens; only SHA-256 digests are stored.
- Refresh-token rotation and consumed-token replay detection that revokes the affected session.
- HttpOnly refresh cookie with Secure enabled in production and SameSite=Strict.
- Active-user/session validation on protected requests; revoked/expired sessions invalidate access tokens.
- Logout, logout-all, current-user profile, session listing and owner-scoped session revocation.
- Authentication API integration tests and security primitive tests.
- Authentication architecture and known-limitations documentation.

Remaining:
- Run CI and resolve any failing tests before merging.
- Validate migrations and refresh-token concurrency behavior on PostgreSQL.
- Add login/register rate limiting before public deployment.
- Add email verification, password reset, and account recovery.
- Add CSRF protection if deployment topology requires cross-site cookies; current design assumes same-site frontend/API.
- Consider account lockout/abuse monitoring and security audit events.
- Add lint/type-check rules and coverage thresholds.

## Phase 4 — PDF ingestion

- Validate actual PDF content, file size, page count and rendered page dimensions.
- Generate safe storage identifiers; keep uploads outside the public web root.
- Extract PDF metadata and distinguish digital/scanned/mixed pages where feasible.
- Add retention and deletion behavior.

## Phase 5 — OCR adapters

- Define a normalized adapter contract.
- Add Tesseract, EasyOCR, PaddleOCR and docTR as independent adapters.
- Pin/document system dependencies and model versions.
- Test normalized outputs and isolate engine-specific failures.

## Phase 6 — Benchmark execution and evaluation

- Add queue/worker execution and explicit benchmark state transitions.
- Run engines on identical page images and record configuration/version information.
- Capture timing, throughput and resource metrics.
- Calculate CER/WER only when a reference transcription is supplied; never present word count as accuracy.

## Phase 7 — Frontend and reporting

- React/TypeScript app with authentication, upload, benchmark configuration, history and results.
- Charts for latency, throughput, memory and ground-truth metrics.
- CSV/PDF exports and clear labeling of unavailable metrics.

## Phase 8 — Hardening and deployment

- Security, integration and representative-corpus tests.
- Docker Compose for frontend, API, PostgreSQL, Redis and workers when those components exist.
- Operational runbooks, retention policy, monitoring and reproducible environment setup.

## Validation policy

For each implementation phase:
1. Run Python compilation and focused tests.
2. Run the full backend test suite.
3. Confirm CI status before describing checks as passing.
4. Test migrations against PostgreSQL when schema changes are introduced.
5. Report unexecuted checks and external prerequisites explicitly.

Dependency installation, database connectivity, migration execution, OCR model downloads and source compilation are distinct checks and must not be conflated.
