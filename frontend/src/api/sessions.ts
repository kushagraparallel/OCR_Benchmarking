import { api } from '../lib/apiClient'
import type { MessageResponse, SessionSummary } from '../lib/types'

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await api.get<{ items: SessionSummary[] }>('/sessions')
  return response.items
}

export function revokeSession(id: string): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/sessions/${id}`)
}
