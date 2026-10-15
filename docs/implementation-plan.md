# OCRLab Implementation Plan

This document is the source of truth for implemented scope, outstanding work, and validation criteria. Update it whenever implementation status changes.

## Status summary

| Phase | Status | Notes |
|---|---|---|
| 1. Repository and API foundation | Implemented; CI verified | FastAPI app factory, typed settings, versioned health endpoint and automated checks |
| 2. Persistence foundation | Implemented foundation; PostgreSQL validation pending | SQLAlchemy engine/session/base, repositories and Alembic migrations |
| 3. Authentication and sessions | Implemented; baseline CI passing | Argon2id, JWT access tokens, hashed rotating refresh tokens, revocation and session endpoints |
| 4. PDF ingestion | Implemented; CI verified | Validated uploads, private local storage, metadata, ownership checks and lifecycle API |
| 5. OCR adapters and PDF rendering | In progress; shared contract, Tesseract, PDF renderer, and optional EasyOCR/PaddleOCR/docTR adapters implemented | Normalized result schema, bounded incremental rendering, lazy model initialization for three optional engines, normalized detection output, mocked adapter tests; native engine validation pending |
| 6. Benchmark execution and evaluation | In progress | Engine factory, bounded runner, PostgreSQL-backed job queue, authenticated lifecycle API, worker leases, cooperative cancellation, and mocked/API tests implemented; PostgreSQL integration, native engines, evaluation metrics and hard process isolation remain |
| 7. Frontend and reporting | Not started | React UI, charts and exports |
| 8. Hardening and deployment | Partial foundations only | CI and security docs exist; production hardening and deployment remain |

## Phase 1 — Repository and API foundation

Implemented:
- Repository overview and phased plan.
- Environment-based Pydantic settings.
- FastAPI application factory and /api/v1/health.
- Initial API tests and pinned dependencies.
- GitHub Actions workflow for Python compilation, migration SQL generation and pytest.

Previously verified:
- CI passed on commit \`6322d4c293ff78ca6f0ae5bb867c04fe016972c2\`: compilation, offline Alembic SQL generation and 14 tests.
- Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38720555786

Remaining:
- Re-run CI for the current document-ingestion changes.
- Add linting and type checking with pinned tool versions.
- Add request IDs and consistent structured error responses in a later hardening pass.

## Phase 2 — Persistence foundation

Implemented:
- SQLAlchemy 2.x engine factory with connection pre-ping.
- Shared application engine and session factory.
- Request-scoped session dependency with rollback on propagated exceptions.
- Shared declarative base and repository layer.
- Alembic configuration and migrations for users, user_sessions, refresh_tokens and documents.
- SQLite-backed unit-test support.

Remaining:
- Verify migration upgrade/downgrade against PostgreSQL.
- Add PostgreSQL service-backed CI integration tests.
- Review schema diffs and migration naming on each schema change.

## Phase 3 — Authentication and sessions

Implemented:
- Registration with email normalization and duplicate-email conflict response.
- Argon2id password hashing and generic invalid-credential responses.
- Short-lived JWT access tokens with issuer, audience, expiry, token ID and session ID claims.
- Opaque high-entropy refresh tokens; only SHA-256 digests are stored.
- Refresh-token rotation and consumed-token replay detection that revokes the affected session.
- HttpOnly refresh cookie with Secure enabled in production and SameSite=Strict.
- Active-user/session validation on protected requests.
- Logout, logout-all, current-user profile, session listing and owner-scoped session revocation.
- Authentication API tests and security primitive tests.

Remaining:
- Add PostgreSQL migration and refresh-concurrency tests.
- Add login/register rate limiting before public deployment.
- Add email verification, password reset and account recovery.
- Add CSRF protection if deployment topology requires cross-site cookies.
- Consider account lockout/abuse monitoring and security audit events.
- Add lint/type-check rules and coverage thresholds.

## Phase 4 — PDF ingestion

Implemented in this step:
- Add a document metadata ORM model and versioned Alembic migration.
- Add a repository with owner-scoped lookup, listing and deletion.
- Stream uploaded content into private staging storage in bounded chunks; enforce byte limits and calculate SHA-256.
- Validate PDF signature and parser readability; reject empty, malformed, encrypted, zero-page, too-many-page, and excessive-dimension documents.
- Sanitize the display filename and generate server-side storage keys.
- Persist bounded metadata and expose authenticated upload/list/get/delete endpoints.
- Keep internal storage paths and content digests out of API responses.
- Add tests for valid uploads, malformed input, size/page limits, authentication, UUID validation, lifecycle and cross-user isolation.

Remaining / known limitations:
- CI passed on commit `c862ecbab097837ca3c529ec5d0feafbedcb918e`: compileall, offline Alembic SQL generation, and 21 tests passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38724195724
- Test migrations against PostgreSQL.
- Add periodic orphan-file reconciliation for crashes and filesystem/database failures.
- Add a storage interface and private object-storage adapter before multi-instance deployment.
- Add antivirus/malware scanning, retention automation, upload-rate limits and deployment-level request-body limits.
- Implement PDF page rendering, digital/scanned page classification and extraction of page images.
- Evaluate page-dimension limits against expected real-world PDFs and add fixtures for malformed/encrypted edge cases.

## Phase 5 — OCR adapters

Implemented:
- Add immutable common input/output data classes with one-based page identity, text, word-level confidence, pixel bounding boxes, engine identity/version and OCR-call timing.
- Define an abstract adapter contract that is independent of engine-specific packages.
- Add domain exceptions for unavailable dependencies, invalid image inputs, and engine execution failures.
- Implement Tesseract using `pytesseract.image_to_data`, preserving line breaks and normalizing confidence and coordinates.
- Implement optional EasyOCR adapter with lazy imports/model initialization, reusable reader instance, explicit model-download policy, and a lock around model inference.
- Normalize EasyOCR polygon bounds and convert its 0–1 confidence to the common 0–100 representation.
- Add a separate optional dependency requirements file so base API installation does not install PyTorch unnecessarily.
- Add EasyOCR unit tests that mock model initialization and do not download models.
- Validate image bytes and bound decoded image pixel count; apply a subprocess timeout.
- Pin `Pillow` and `pytesseract` dependencies and document the separate native Tesseract executable/language-data requirement.
- Add mocked-engine tests that do not require Tesseract installed in CI.

Verified on commit `b2bd38c5e809f990f4dbb444904964191a2ee36d`: compilation, offline Alembic SQL generation, and all 27 tests passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38728100165

Verified on commit `a56731e5b17598ba49a514ab54b3156de4fd1c01`: Python compilation, offline Alembic SQL generation, and the backend test suite passed. Run: https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38732468400

Remaining validation:
- Run a native Tesseract smoke test in an environment with the executable and English trained data installed.
- Review OCR text ordering and confidence normalization against a representative corpus.

Remaining:
- Validate EasyOCR, PaddleOCR, and docTR on real documents with model files pre-provisioned; measure cold-start time, inference latency, and memory.
- Add optional docTR adapter with a required predictor factory so architecture and local-weight policy remain application-controlled.
- Normalize docTR export page dimensions, relative word geometry, confidence, empty output, and malformed result errors.
- Add a pinned optional docTR/PyTorch dependency file and mocked adapter tests.
- Add an adapter registry/factory after the initial adapters are validated.
- Persist engine configuration/version metadata with benchmark results.
- Add native-runtime CI coverage and multilingual fixtures.

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
1. Inspect current files and callers before modifying them.
2. Run Python compilation and focused tests.
3. Run the full backend test suite.
4. Confirm CI status before describing checks as passing.
5. Test migrations against PostgreSQL when schema changes are introduced.
6. Report unexecuted checks and external prerequisites explicitly.

Dependency installation, database connectivity, migration execution, OCR model downloads and source compilation are distinct checks and must not be conflated.


## Phase 6 — Benchmark orchestration (in progress)

Implemented in this step:
- Add a common OCR engine factory with deterministic engine discovery, duplicate/unknown-name validation, and lazy optional-engine registration. (Implemented.)
- Add validated benchmark configuration for engine timeout, concurrent inferences, and aggregate rendered-image byte budget.
- Render PDF pages incrementally once and pass the same immutable encoded page bytes to each selected engine.
- Execute synchronous rendering and OCR in worker threads so they do not block the FastAPI event loop.
- Bound OCR inference concurrency and retain a concurrency slot until a timed-out/cancelled native call actually finishes.
- Record per-engine status, duration, bounded error details, and normalized per-page OCR results; isolate engine exceptions.
- Add mocked tests for registry validation, partial failure, shared page bytes, timeout isolation, cancellation propagation, concurrency, oversized PDF page count, and image-byte budgets.

Important limitations:
- The OCR runner itself is an in-process service invoked by a durable database-backed worker. API requests enqueue work; worker restarts are recoverable through expiring database leases.
- Python cannot forcibly terminate arbitrary native OCR work already running in a thread. Timeouts report the result and keep the concurrency slot reserved until the call exits; process isolation remains required for hard-kill guarantees.
- The aggregate rendered-image budget limits total bytes rendered over a run, not just peak resident memory. It is intentionally conservative and configurable.
- Optional engine configuration must supply vetted local model paths/factories; no request-time model downloads are enabled.
- Native OCR engine smoke tests and real-model memory profiling remain pending.


## Phase 6 follow-up — durable benchmark jobs

Implemented on the current branch:
- Added the benchmark_jobs ORM model and migration 20261015_0003, persisting owner, source document, engine selection, status, attempt count, timestamps, lease, JSON result and error.
- Added authenticated endpoints: GET /api/v1/benchmarks/engines, POST /api/v1/benchmarks (202 Accepted), GET /api/v1/benchmarks, GET /api/v1/benchmarks/{job_id}, and DELETE /api/v1/benchmarks/{job_id}. Job history and status are owner-scoped.
- Added a database-backed polling worker. PostgreSQL FOR UPDATE SKIP LOCKED coordinates claims across worker processes; leases are renewed during execution and expired running jobs can be recovered up to OCR_WORKER_MAX_ATTEMPTS.
- Added cooperative cancellation at page boundaries and worker-local adapter reuse so model initialization is amortized across jobs.
- Added configured engine selection. Tesseract is enabled by default; EasyOCR and PaddleOCR require explicit local model directories. docTR remains unavailable through the worker registry until its predictor factory/model-loading configuration is provided.
- Added tests for authenticated job submission/history/cancellation/ownership, queue claims, lease renewal, and existing OCR orchestration failure/resource scenarios.

Operations:
- From backend/, apply migrations with `alembic upgrade head`, then run `python -m app.workers.benchmark_worker` in one or more separate worker processes.
- All workers must share the same PostgreSQL database and, with current local document storage, the same DOCUMENT_STORAGE_ROOT.
- Worker count controls concurrent jobs across processes. OCR_MAX_CONCURRENT_ENGINES controls inference concurrency inside each job, so the approximate upper bound is worker count multiplied by that setting. Keep both conservative until memory profiling is complete.

Remaining work:
- Run migration upgrade/downgrade and concurrent-claim/lease-recovery tests against real PostgreSQL; SQLite cannot verify PostgreSQL row-lock semantics.
- Add hard process isolation for enforceable termination and memory ceilings for native OCR calls.
- Configure docTR predictor/model loading; run native Tesseract, EasyOCR, and PaddleOCR smoke tests with provisioned local models.
- Add peak RSS, CPU, cold-start, word count, CER/WER, reference-ground-truth scoring, queue metrics, job retention, and operational health/runbooks.
- Confirm that deployed workers use shared document storage when running on separate hosts.
