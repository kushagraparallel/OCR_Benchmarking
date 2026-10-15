import { api } from '../lib/apiClient'
import type { BenchmarkJob, BenchmarkJobListResponse } from '../lib/types'

export function listAvailableEngines(): Promise<string[]> {
  return api.get<string[]>('/benchmarks/engines')
}

export function submitBenchmark(documentId: string, engineNames: string[]): Promise<BenchmarkJob> {
  return api.post<BenchmarkJob>('/benchmarks', { document_id: documentId, engine_names: engineNames })
}

export function listBenchmarks(limit = 20, offset = 0): Promise<BenchmarkJobListResponse> {
  return api.get<BenchmarkJobListResponse>(`/benchmarks?limit=${limit}&offset=${offset}`)
}

export function getBenchmark(id: string): Promise<BenchmarkJob> {
  return api.get<BenchmarkJob>(`/benchmarks/${id}`)
}

export function cancelBenchmark(id: string): Promise<BenchmarkJob> {
  return api.delete<BenchmarkJob>(`/benchmarks/${id}`)
}
