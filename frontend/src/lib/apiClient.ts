import type { ApiErrorBody } from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
export const API_PREFIX = '/api/v1'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Held in memory only. The long-lived credential is the HttpOnly refresh
// cookie the backend sets; losing this on reload is recovered via /auth/refresh.
let accessToken: string | null = null
let onUnauthorized: (() => void) | null = null
let refreshInFlight: Promise<string | null> | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

export function registerUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail.map((item) => item.msg).join(' ')
    }
  } catch {
    // Response had no JSON body; fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}${API_PREFIX}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        })
        if (!response.ok) return null
        const data = (await response.json()) as { access_token: string }
        accessToken = data.access_token
        return data.access_token
      } catch {
        return null
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

interface RequestOptions {
  method?: string
  body?: unknown
  isForm?: boolean
  skipAuthRetry?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, isForm = false, skipAuthRetry = false } = options

  const headers: Record<string, string> = {}
  if (!isForm && body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  })

  if (response.status === 401 && !skipAuthRetry && !path.startsWith('/auth/')) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      return request<T>(path, { ...options, skipAuthRetry: true })
    }
    onUnauthorized?.()
    throw new ApiError(401, 'Your session has expired. Please sign in again.')
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response))
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  postForm: <T>(path: string, body: FormData) => request<T>(path, { method: 'POST', body, isForm: true }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  refreshAccessToken,
}
