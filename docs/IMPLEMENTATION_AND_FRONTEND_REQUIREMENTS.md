# OCR Benchmarking — Implementation Inventory, Remaining Work, and Frontend Requirements

**Status date:** 2026-10-15  
**Branch:** `feat/backend-foundation`  
**Related pull request:** [PR #6 — Durable benchmark jobs and global worker limits](https://github.com/kushagraparallel/OCR_Benchmarking/pull/6)

This is the single source of truth for what has been implemented, what is validated, what remains, and the required frontend experience. Statuses distinguish code present from production validation; a green CI run does not imply native OCR engines or real PostgreSQL deployment behavior have been fully validated.

## 1. Project goal

Build a reliable OCR benchmarking application that accepts PDFs, runs selected OCR engines against identical rendered page images, reports normalized text and engine output, and compares accuracy and operational performance. The system must be reproducible, resource-bounded, secure, observable, and usable through a React frontend.

Primary comparison dimensions:
- OCR text and word/character counts
- Runtime and per-page latency
- Accuracy against optional ground truth (CER/WER and related measures)
- CPU and peak memory usage, where reliably measurable
- Engine status, errors, configuration, and reproducibility metadata

## 2. Implemented so far

### Backend foundation and code standards
- FastAPI backend organized into API, core/service, database model/repository, and worker layers.
- Typed settings/configuration and pinned core dependencies, with optional OCR engine dependencies separated where appropriate.
- Module-level logging, typed interfaces, error handling, and unit tests in the existing backend test suite.
- Documentation and implementation tracking in this file and the OCR README.

### Authentication, sessions, and document handling
- Authentication/session foundations and owner-scoped access controls.
- PDF upload/validation and private document storage.
- Document validation limits including upload size, page count, and page raster dimensions.
- Document storage access is checked before a benchmark can be queued.

### OCR adapters and rendering
- Common OCR adapter contract and normalized OCR result schema.
- Tesseract adapter.
- Optional EasyOCR and PaddleOCR adapters, with explicit local model configuration and no implicit request-time downloads.
- docTR adapter with explicit predictor injection to avoid surprise pretrained model downloads.
- PDF page renderer with bounded rendering and page-level image output.
- Common engine registry/factory for enabled engines and engine-name validation.
- Benchmark runner renders a page once and shares the same rendered image bytes with every selected engine.
- Synchronous OCR calls are dispatched away from the FastAPI event loop.
- Engine outcomes are isolated: one engine's error is represented independently instead of discarding other engines' results.
- Per-engine status, normalized output, elapsed duration, and bounded error details are represented in benchmark results.
- Per-engine timeout, inference concurrency, and cumulative rendered-image byte budget are supported by the runner.
- PDF iterator is advanced on a dedicated single thread to avoid migrating a PyMuPDF document iterator across threads.
- Native OCR work that outlives a soft timeout remains tracked so inference capacity is not incorrectly released early.

### Durable benchmark jobs and API
- Database-backed benchmark job records, lifecycle status, attempts, leases, timestamps, JSON results, and error storage.
- Authenticated endpoints:
  - `GET /api/v1/benchmarks/engines` — enabled engines.
  - `POST /api/v1/benchmarks` — validate request and enqueue; returns HTTP 202.
  - `GET /api/v1/benchmarks` — owner-scoped paginated history.
  - `GET /api/v1/benchmarks/{job_id}` — owner-scoped status/result.
  - `DELETE /api/v1/benchmarks/{job_id}` — cancel queued work or request cooperative cancellation.
- Separate worker entry point: `python -m app.workers.benchmark_worker`.
- PostgreSQL job claiming uses `FOR UPDATE SKIP LOCKED`; job leases are renewed and expired jobs can be recovered.
- Shared PostgreSQL worker capacity slots cap active benchmark jobs across worker processes. Slots have renewable leases and can be recovered after worker loss.
- Adapter/model instances are reused within a worker process.
- Worker-wide inference concurrency remains bounded across jobs, including when an OCR thread has timed out but has not returned.

### Migrations and documentation
- Migration `20261015_0003`: benchmark job persistence.
- Migration `20261015_0004`: shared worker capacity slots.
- `backend/app/core/ocr/README.md` documents adapter/runner configuration and usage.
- The current implementation branch has a draft PR: [PR #6](https://github.com/kushagraparallel/OCR_Benchmarking/pull/6).

### Current CI evidence
The latest recorded CI run succeeded:
[GitHub Actions run 38763856650](https://github.com/kushagraparallel/OCR_Benchmarking/actions/runs/38763856650).

It completed Python compilation, offline Alembic migration SQL generation, and the backend test suite (73 tests passed at the time recorded). This is not a substitute for live PostgreSQL concurrency tests or native OCR model smoke tests.

## 3. Remaining backend work

Statuses below are intentionally conservative.

### P0 — Validate correctness and reliability before production

- [ ] **Live PostgreSQL integration tests**
  - Run two or more independent worker sessions against PostgreSQL.
  - Prove only one worker claims a queued job.
  - Test slot acquisition, `SKIP LOCKED`, renewal, expiry, and release under concurrency.
  - Test migrations upgrade from the supported base revision and downgrade in a disposable database.
  - Verify database timezone behavior, transaction boundaries, and recovery after abrupt process termination.
- [ ] **End-to-end worker failure/recovery tests**
  - Kill a worker while it is rendering, waiting for an engine, running an engine, and saving results.
  - Verify lease expiry and bounded retry count.
  - Ensure a job cannot be marked complete after ownership/lease is lost.
  - Verify terminal states and partial results remain consistent.
- [ ] **Cancellation semantics**
  - Test queued cancellation, cancellation between pages, cancellation during a native OCR call, and cancellation after completion.
  - Document that Python thread cancellation is cooperative only.
  - Confirm active capacity is held until native calls actually return.
  - Ensure shutdown does not accidentally mark incomplete work as successful.
- [ ] **Resource-limit integration tests**
  - Oversized upload, excessive PDF pages, oversized raster dimensions, and cumulative rendered-image budget.
  - Verify rejection occurs before expensive work where possible.
  - Verify a single oversized page or malformed PDF does not crash the worker.
- [ ] **Native OCR smoke tests**
  - Run Tesseract with the supported binary/language packs.
  - Run EasyOCR and PaddleOCR only with explicitly provisioned local model directories.
  - Configure and test docTR's predictor factory/weights without implicit network downloads.
  - Record tested OS, Python, package, model, and language versions.
- [ ] **Fix/verify timeout and cancellation edge cases**
  - Verify exception types and statuses are consistent between engine failures and timeouts.
  - Confirm elapsed time includes the intended work and is not misleading when work continues after a timeout.
  - Ensure all outstanding tasks/futures are observed and exceptions logged.
- [ ] **Security review**
  - Validate file access and ownership on every API path.
  - Limit request payloads and page/image sizes.
  - Avoid returning stack traces, secrets, absolute storage paths, or raw sensitive OCR text in logs.
  - Add rate limits/quotas if the deployment is exposed to untrusted users.
  - Review CORS, token expiry/revocation, upload MIME/signature validation, and private storage permissions.

### P1 — Finish benchmark value and observability

- [ ] **Accuracy metrics**
  - Add a ground-truth upload/association workflow.
  - Implement character error rate (CER) and word error rate (WER), including normalization rules.
  - Define treatment of whitespace, punctuation, case, Unicode, hyphenation, and page boundaries.
  - Unit-test empty references, empty hypotheses, and edge cases.
- [ ] **Performance metrics**
  - Capture render time, per-engine/per-page inference time, total wall time, queue wait time, and cold-start time separately.
  - Measure CPU and peak RSS with documented methodology; distinguish process-wide from per-engine attribution.
  - Record page count, image dimensions, image bytes, engine versions, and model/config identifiers.
  - Never imply precise per-engine memory attribution when only process-level measurements exist.
- [ ] **Structured result schema and versioning**
  - Version stored result JSON.
  - Persist engine/version/config metadata so historical runs are interpretable.
  - Preserve partial successes and page-level outputs if another engine fails.
  - Define result retention and output-size limits.
- [ ] **Queue/worker observability**
  - Structured lifecycle logs with job ID, engine name, page number, attempt, and elapsed time; do not log sensitive OCR content.
  - Worker health/readiness checks and queue-depth/oldest-job monitoring.
  - Metrics for queue wait, throughput, failures, retries, timeout count, slot occupancy, and resource pressure.
  - Alerting and operational runbooks for stuck jobs, lost leases, full disk, and OOM kills.
- [ ] **Storage and deployment**
  - Ensure all worker replicas share the same document storage or use object storage.
  - Define worker shutdown/drain behavior and deployment health checks.
  - Define retention/cleanup for uploaded documents, rendered images, result payloads, and old jobs.
  - Confirm migrations are applied by deployment tooling, not implicitly by every API process.
- [ ] **Optional engine support**
  - Expose docTR model construction/configuration in the registry without hidden downloads.
  - Provide a clear supported-engine capability/configuration endpoint.
  - Add reproducible engine installation and local model setup docs for Windows and Linux.

### P2 — Product improvements

- [ ] Benchmark templates/presets and saved engine configurations.
- [ ] Retry selected failed engines without rerunning successful engines, if result semantics support this safely.
- [ ] Export results as CSV/JSON and a shareable report format.
- [ ] Dataset/corpus management and repeatable benchmark suites.
- [ ] Compare multiple runs and compute medians/percentiles.
- [ ] Optional Celery/Redis queue if operational requirements justify it; the current design uses PostgreSQL polling.
- [ ] Process-isolated OCR execution for hard timeouts and stronger memory isolation. This requires careful model lifecycle and IPC design, not simply wrapping existing objects in a process pool.

## 4. Frontend requirements — detailed implementation specification

### 4.1 Technology and architecture
- React + TypeScript + Vite.
- Tailwind CSS and the project's existing shadcn/ui component system.
- Recharts for charts where useful.
- React Router for page routing.
- TanStack Query (or the established project equivalent) for server state, polling, cache invalidation, and request cancellation.
- React Hook Form + Zod (or equivalent established form tooling) for typed form validation.
- A centralized typed API client; do not scatter raw `fetch` calls across components.
- Reusable components, accessible forms, responsive layouts, loading/error/empty states, and consistent design tokens.
- Keep authentication, API transport, feature components, and presentation components separated.
- Do not put long-running OCR processing in the browser; the frontend submits a job and polls its persisted state.

### 4.2 Routes and pages

#### A. Authentication
- [ ] Login page with email/username and password according to backend contract.
- [ ] Registration page only if account creation is enabled by the backend.
- [ ] Session-expired handling and a clear re-login path.
- [ ] Logout action that revokes/ends the current session where supported.
- [ ] Do not store long-lived refresh tokens in localStorage. Follow the backend's cookie/token design and CSRF requirements.

#### B. Main application shell
- [ ] Responsive sidebar/navigation with Dashboard, New Benchmark, Benchmark History, Documents, and Settings/Account as supported by the backend.
- [ ] Header with page title, user/account menu, and session status.
- [ ] Breadcrumbs for detail pages.
- [ ] Consistent content width, spacing, typography, keyboard focus, and accessible color contrast.
- [ ] Mobile layout that collapses navigation without hiding primary actions.

#### C. Dashboard
- [ ] Summary cards: total jobs, successful jobs, partial failures, failed jobs, and queued/running jobs over a clearly defined time window.
- [ ] Recent benchmark table with status, document, engines, submitted time, duration, and action to open details.
- [ ] Charts for run volume/status distribution and latency trends only when the API provides sufficient data.
- [ ] Empty state with a prominent “New benchmark” action.
- [ ] Loading skeletons, retryable error state, and no fabricated metrics when backend data is unavailable.
- [ ] Do not show aggregate metrics that the backend does not yet calculate.

#### D. Documents
- [ ] Upload PDF using drag-and-drop and a normal file picker.
- [ ] Display selected file name, file size, upload progress if supported, and validation errors.
- [ ] Show configured upload/page limits returned by backend if exposed.
- [ ] Validate obvious client-side constraints for usability, but always treat server validation as authoritative.
- [ ] Document list with name, pages, size, upload date, and available actions based on backend capabilities.
- [ ] Handle invalid PDF, corrupt file, too-large file, unsupported type, and expired/unauthorized session.
- [ ] Never render uploaded file contents as trusted HTML.

#### E. New Benchmark wizard
- [ ] Step 1: choose an existing uploaded PDF or upload a new one.
- [ ] Step 2: fetch available engines from `GET /api/v1/benchmarks/engines`; show display name, installed/enabled status, and configuration requirements.
- [ ] Step 3: select one or more engines; prevent empty selection and duplicate engine names.
- [ ] Step 4: show a review panel with document, page count, engine selection, and any known runtime/resource caveats.
- [ ] Step 5: submit via `POST /api/v1/benchmarks`; on HTTP 202 navigate to the job detail page.
- [ ] Disable duplicate submission while the request is pending.
- [ ] Show actionable API validation messages without exposing stack traces.
- [ ] If no engines are enabled, explain that engine installation/configuration is required rather than presenting an unusable selector.
- [ ] If benchmark options (timeout, concurrency, ground truth) are not supported by the backend contract, do not expose them as if they take effect.

#### F. Benchmark history
- [ ] Paginated table with job ID/short ID, document, selected engines, status, created time, duration, and result availability.
- [ ] Filters for status, date range, engine, and document where supported.
- [ ] Sort by submitted time and duration if API supports it.
- [ ] Clear filter/reset state and meaningful no-results state.
- [ ] Use server-side pagination and filtering for large histories; don't fetch the entire history and filter only in the browser.
- [ ] Poll only active jobs; stop polling terminal jobs and on unmount.
- [ ] Keep pagination/filter state in URL query parameters where practical.

#### G. Benchmark detail/results
- [ ] Header with document name, job status, submission time, start/finish times, and total elapsed time.
- [ ] Clear lifecycle states: queued, running, cancellation requested, cancelled, succeeded, partial success, and failed, matching the final backend enum exactly.
- [ ] Per-engine result cards or tabs showing status, elapsed time, error message, text/word count, and normalized output.
- [ ] A partial-success banner when some engines succeed and others fail; never hide successful outputs because another engine failed.
- [ ] Page selector for multi-page results and per-page text/output if persisted by backend.
- [ ] Copy text, download text/JSON, and export actions only when implemented and authorized by the backend.
- [ ] Render OCR text as plain text; escape/untrusted content and avoid unsafe HTML injection.
- [ ] Long OCR output should be virtualized or collapsed with expand/copy controls.
- [ ] Cancel action only for cancellable states, with confirmation when useful. Reflect that cancellation may wait for active native OCR to return.
- [ ] Retry action only if a supported retry endpoint exists; otherwise do not simulate it.
- [ ] Show safe, bounded error detail and a correlation/job ID for troubleshooting.

#### H. Comparison view
- [ ] Side-by-side engine outputs for the same page, with synchronized page selection.
- [ ] Optional synchronized scrolling and text search.
- [ ] Comparison table for duration, word count, character count, status, and error state.
- [ ] Accuracy metrics such as CER/WER only after backend ground-truth scoring exists.
- [ ] Performance charts should identify units and whether values are per page, per engine, or per run.
- [ ] Do not label word count as accuracy; word count is descriptive, not a quality metric.
- [ ] Show engine/config/version metadata to help reproduce comparisons.

#### I. Settings and help
- [ ] Account/session controls supported by the backend.
- [ ] Display enabled engine capabilities and missing optional engine dependencies.
- [ ] Link to setup/help docs and explain resource limits.
- [ ] Only expose settings that the backend actually accepts and validates.
- [ ] Show app/API version and support diagnostics where available, without exposing secrets or infrastructure internals.

### 4.3 Frontend API client and types
- [ ] Define TypeScript types matching the actual Pydantic response/request models for:
  - Auth/session responses.
  - Uploaded document metadata.
  - Engine capability/configuration metadata.
  - Benchmark create request and accepted response.
  - Benchmark status/history pagination.
  - Per-engine and per-page OCR results.
  - Error envelope and cancellation response.
- [ ] Generate types from OpenAPI if the backend contract is stable, or keep hand-written types verified by contract tests.
- [ ] Centralize base URL, authorization, credentials/cookie handling, JSON parsing, and error normalization.
- [ ] Handle 401/403/404/409/413/422/429/5xx distinctly where applicable.
- [ ] Never assume optional fields exist; handle missing/partial engine results defensively.
- [ ] Add API contract tests or mocked integration tests for successful, partial-success, timeout, cancellation, and unauthorized responses.

### 4.4 Polling and client state
- [ ] Poll queued/running/cancellation-requested jobs with a configurable interval and backoff.
- [ ] Stop polling on terminal states and when a page/component unmounts.
- [ ] Avoid overlapping polls and duplicate mutations.
- [ ] Invalidate/refetch history and dashboard queries after submission or completion.
- [ ] Preserve results when one engine fails.
- [ ] Distinguish network failure from benchmark failure; a temporary UI network error must not mutate the server job state.
- [ ] Show “last updated” time and a manual refresh control.

### 4.5 UX states and accessibility
Every page needs:
- [ ] Initial loading state.
- [ ] Empty state.
- [ ] Recoverable error state with retry.
- [ ] Permission/expired-session state.
- [ ] Success feedback for actions.
- [ ] Keyboard navigation, visible focus, semantic headings/labels, and screen-reader status announcements.
- [ ] Responsive desktop/tablet/mobile behavior.
- [ ] No color-only status encoding; use text/icons as well.
- [ ] Confirmation for destructive or potentially expensive actions.
- [ ] Clear warnings when an operation is still running or cancellation is only requested.

### 4.6 Frontend testing
- [ ] Unit tests for engine selector, upload validation, status badges, error formatting, and result rendering.
- [ ] Component tests for loading, empty, partial-success, timeout, and cancellation states.
- [ ] API mocking tests for authentication errors, validation failures, and server errors.
- [ ] End-to-end flow: login → upload PDF → submit multi-engine benchmark → observe status → inspect successful and failed engine results.
- [ ] End-to-end ownership test: another user cannot access a job by changing its ID.
- [ ] Accessibility checks and responsive viewport smoke tests.
- [ ] Verify no request loop continues polling after a job becomes terminal.

### 4.7 Frontend delivery checklist
- [ ] Confirm the actual frontend directory, package manager, scripts, design system, and existing routes before adding files.
- [ ] Follow existing lint/format/type-check conventions; don't add duplicate dependencies without checking the package manifest.
- [ ] Add an `.env.example` with only non-secret public configuration (e.g. API base URL).
- [ ] Document local startup, required backend URL, auth behavior, tests, and build.
- [ ] Add CI steps for lint, type-check, unit tests, and production build.
- [ ] Keep secrets out of Vite client environment variables; every `VITE_*` variable is public to browser users.

## 5. Suggested implementation sequence

1. Finish P0 live PostgreSQL, cancellation, recovery, and resource-limit tests.
2. Finalize the OpenAPI contract and exact benchmark status/result schemas.
3. Implement frontend app shell and authentication against existing auth APIs.
4. Implement document upload/list and engine discovery.
5. Implement new benchmark wizard and accepted-job navigation.
6. Implement history, job detail, polling, partial results, and cancellation.
7. Implement side-by-side comparison and export actions supported by the backend.
8. Add ground-truth workflow and CER/WER backend before presenting accuracy charts.
9. Add frontend unit/component/E2E tests and CI.
10. Run native model benchmarks, capture resource baselines, then tune concurrency defaults.
11. Add production monitoring, cleanup/retention, deployment and incident runbooks.

## 6. Definition of done

A feature is complete only when code, tests, docs, and operational behavior agree. In particular:
- Identical page images are sent to every selected engine for fair comparisons.
- The API event loop remains responsive while OCR executes.
- Concurrency is bounded across worker processes, not just within one process.
- One engine failure does not erase other engine results.
- Timeouts, cancellation, retries, and worker loss have tested and documented semantics.
- Stored results include enough metadata to reproduce a run.
- UI state matches server state and never fabricates unsupported metrics.
- Security, ownership, limits, and error handling are tested.
- Implemented versus pending claims remain accurate in this document and the README.
