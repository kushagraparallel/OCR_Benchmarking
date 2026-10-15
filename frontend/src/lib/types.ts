// Mirrors backend/app/schemas/*.py and backend/app/core/ocr/benchmark.py exactly.

export interface User {
  id: number
  email: string
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface MessageResponse {
  message: string
}

export interface SessionSummary {
  id: string
  created_at: string
  expires_at: string
  last_used_at: string | null
  user_agent: string | null
}

export interface DocumentSummary {
  id: string
  original_filename: string
  size_bytes: number
  page_count: number
  pdf_title: string | null
  pdf_author: string | null
  status: string
  created_at: string
}

export interface DocumentListResponse {
  items: DocumentSummary[]
  limit: number
  offset: number
}

export type BenchmarkJobStatus =
  | 'queued'
  | 'running'
  | 'cancellation_requested'
  | 'cancelled'
  | 'completed'
  | 'partial'
  | 'failed'

export type EngineStatus = 'success' | 'partial' | 'failed' | 'timed_out'

export interface OCRBoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export interface OCRWord {
  text: string
  bounding_box: OCRBoundingBox
  confidence: number | null
}

export interface OCRPageResult {
  engine_name: string
  engine_version: string
  page_number: number
  text: string
  words: OCRWord[]
  duration_ms: number
}

export interface EngineBenchmarkResult {
  engine_name: string
  status: EngineStatus
  duration_ms: number
  results: OCRPageResult[]
  error: string | null
}

export interface BenchmarkResultPayload {
  status: 'success' | 'partial' | 'failed'
  duration_ms: number
  page_count: number
  engines: Record<string, EngineBenchmarkResult>
}

export interface BenchmarkJob {
  id: string
  document_id: string
  engine_names: string[]
  status: BenchmarkJobStatus
  result: BenchmarkResultPayload | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  attempt_count: number
}

export interface BenchmarkJobListResponse {
  items: BenchmarkJob[]
  limit: number
  offset: number
}

export interface ApiErrorBody {
  detail?: string | { msg: string }[]
}
