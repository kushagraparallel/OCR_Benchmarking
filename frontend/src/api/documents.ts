import { api } from '../lib/apiClient'
import type { DocumentListResponse, DocumentSummary, MessageResponse } from '../lib/types'

export function listDocuments(limit = 20, offset = 0): Promise<DocumentListResponse> {
  return api.get<DocumentListResponse>(`/documents?limit=${limit}&offset=${offset}`)
}

export function getDocument(id: string): Promise<DocumentSummary> {
  return api.get<DocumentSummary>(`/documents/${id}`)
}

export function uploadDocument(file: File): Promise<DocumentSummary> {
  const form = new FormData()
  form.append('file', file)
  return api.postForm<DocumentSummary>('/documents', form)
}

export function deleteDocument(id: string): Promise<MessageResponse> {
  return api.delete<MessageResponse>(`/documents/${id}`)
}
