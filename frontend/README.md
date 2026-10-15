# OCRLab frontend

React + TypeScript console for the OCRLab API: upload PDFs, launch OCR engine benchmarks, and compare per-page, per-engine results.

## Stack

- Vite + React 19 + TypeScript
- React Router for client-side routing
- TanStack Query for data fetching, caching, and polling job status
- Plain CSS (design tokens in `src/styles/`) — no UI framework

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # set VITE_API_BASE_URL if the API isn't on localhost:8000
npm run dev
```

The dev server runs at `http://localhost:5173`, which matches the backend's default `CORS_ORIGINS`. The backend must be running (see `backend/README.md`) with PostgreSQL migrated and at least one OCR engine enabled.

## Auth model

- Login/refresh return a short-lived JSON access token, kept in memory only (`src/lib/apiClient.ts`).
- The backend also sets an HttpOnly refresh cookie. On app load, `AuthProvider` silently calls `/auth/refresh` (`credentials: 'include'`) to restore a session after a page reload, without ever storing the refresh token in JS.
- A 401 on any authenticated request triggers one transparent refresh-and-retry; if that fails, the user is routed to `/login`.

## Structure

```
src/
  api/        One module per backend resource (auth, documents, benchmarks, sessions)
  lib/        Fetch client, shared types mirroring backend schemas, formatting helpers
  context/    AuthContext (session bootstrap, login/register/logout)
  components/ Shared UI: layout shell, status badges, modals, dropzone, icons
  pages/      One component per route
```

## Routes

| Path | Purpose |
|---|---|
| `/login`, `/register` | Unauthenticated |
| `/documents` | Upload PDFs, list owned documents, launch a benchmark |
| `/benchmarks` | Job history, polls while any job is active |
| `/benchmarks/:jobId` | Per-engine, per-page OCR results; polls while queued/running |
| `/sessions` | Active sessions for the account; revoke one or all |

## Build

```bash
npm run build   # tsc -b && vite build
```
