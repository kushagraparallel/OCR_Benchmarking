import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { cancelBenchmark, getBenchmark } from '../api/benchmarks'
import { getDocument } from '../api/documents'
import { Alert } from '../components/Alert'
import { ConfirmModal } from '../components/ConfirmModal'
import { PageHeader } from '../components/PageHeader'
import { LoadingRow, Spinner } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { StopIcon } from '../components/icons'
import { ApiError } from '../lib/apiClient'
import { averageConfidence, engineDisplayName, formatConfidence, formatDateTime, formatDuration } from '../lib/format'
import type { EngineBenchmarkResult } from '../lib/types'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancellation_requested'])
const CANCELLABLE_STATUSES = new Set(['queued', 'running'])

export function BenchmarkDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const queryClient = useQueryClient()
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)
  const [activeEngine, setActiveEngine] = useState<string | null>(null)
  const [activePage, setActivePage] = useState(1)

  const jobQuery = useQuery({
    queryKey: ['benchmark', jobId],
    queryFn: () => getBenchmark(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data && ACTIVE_STATUSES.has(query.state.data.status) ? 2000 : false),
  })

  const job = jobQuery.data

  const documentQuery = useQuery({
    queryKey: ['document', job?.document_id],
    queryFn: () => getDocument(job!.document_id),
    enabled: Boolean(job?.document_id),
  })

  const cancelMutation = useMutation({
    mutationFn: () => cancelBenchmark(jobId as string),
    onSuccess: () => {
      setShowCancelConfirm(false)
      void queryClient.invalidateQueries({ queryKey: ['benchmark', jobId] })
      void queryClient.invalidateQueries({ queryKey: ['benchmarks'] })
    },
  })

  if (jobQuery.isLoading) {
    return (
      <>
        <PageHeader title="Benchmark" />
        <div className="page-content">
          <LoadingRow label="Loading benchmark job…" />
        </div>
      </>
    )
  }

  if (jobQuery.isError || !job) {
    return (
      <>
        <PageHeader title="Benchmark" />
        <div className="page-content">
          <Alert message="This benchmark job could not be found." />
        </div>
      </>
    )
  }

  const engines = job.result ? Object.values(job.result.engines) : []
  const currentEngine: EngineBenchmarkResult | undefined =
    engines.find((engine) => engine.engine_name === activeEngine) ?? engines[0]
  const currentPageResult = currentEngine?.results.find((page) => page.page_number === activePage) ?? currentEngine?.results[0]

  return (
    <>
      <PageHeader
        title="Benchmark run"
        subtitle={`Job ${job.id}`}
        actions={
          CANCELLABLE_STATUSES.has(job.status) ? (
            <button className="btn btn-danger" onClick={() => setShowCancelConfirm(true)}>
              <StopIcon width={14} height={14} />
              Cancel
            </button>
          ) : undefined
        }
      />
      <div className="page-content">
        <div className="breadcrumb">
          <Link to="/benchmarks">Benchmarks</Link>
          <span>/</span>
          <span className="cell-id">{job.id.slice(0, 8)}</span>
        </div>

        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-pad">
            <div className="section-title-row">
              <StatusBadge status={job.status} />
              {ACTIVE_STATUSES.has(job.status) && <Spinner />}
            </div>

            <div className="stat-grid" style={{ marginBottom: 16 }}>
              <div className="stat-tile">
                <div className="stat-tile-label">Document</div>
                <div className="stat-tile-value" style={{ fontSize: 14 }}>
                  {documentQuery.data?.original_filename ?? job.document_id.slice(0, 8)}
                </div>
              </div>
              <div className="stat-tile">
                <div className="stat-tile-label">Engines</div>
                <div className="stat-tile-value" style={{ fontSize: 14 }}>
                  {job.engine_names.map(engineDisplayName).join(', ')}
                </div>
              </div>
              <div className="stat-tile">
                <div className="stat-tile-label">Pages</div>
                <div className="stat-tile-value">{job.result?.page_count ?? '—'}</div>
              </div>
              <div className="stat-tile">
                <div className="stat-tile-label">Total duration</div>
                <div className="stat-tile-value">{job.result ? formatDuration(job.result.duration_ms) : '—'}</div>
              </div>
            </div>

            <div className="inline-meta">
              <span>
                Created: <strong>{formatDateTime(job.created_at)}</strong>
              </span>
              <span>
                Started: <strong>{formatDateTime(job.started_at)}</strong>
              </span>
              <span>
                Finished: <strong>{formatDateTime(job.finished_at)}</strong>
              </span>
              <span>
                Attempts: <strong>{job.attempt_count}</strong>
              </span>
            </div>

            {job.error && (
              <div style={{ marginTop: 16 }}>
                <Alert message={job.error} />
              </div>
            )}
          </div>
        </div>

        {engines.length > 0 && currentEngine && (
          <div className="card">
            <div className="tabs" style={{ padding: '0 20px' }}>
              {engines.map((engine) => (
                <button
                  key={engine.engine_name}
                  className={`tab-btn${engine.engine_name === currentEngine.engine_name ? ' active' : ''}`}
                  onClick={() => {
                    setActiveEngine(engine.engine_name)
                    setActivePage(1)
                  }}
                >
                  {engineDisplayName(engine.engine_name)}
                  <StatusBadge status={engine.status} />
                </button>
              ))}
            </div>

            <div className="card-pad">
              <div className="inline-meta" style={{ marginBottom: 16 }}>
                <span>
                  Engine duration: <strong>{formatDuration(currentEngine.duration_ms)}</strong>
                </span>
                <span>
                  Pages recognized: <strong>{currentEngine.results.length}</strong>
                </span>
              </div>

              {currentEngine.error && <Alert message={currentEngine.error} />}

              {currentEngine.results.length > 0 && currentPageResult && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-700)' }}>Page</span>
                    <select
                      className="input"
                      style={{ width: 100 }}
                      value={currentPageResult.page_number}
                      onChange={(event) => setActivePage(Number(event.target.value))}
                    >
                      {currentEngine.results.map((page) => (
                        <option key={page.page_number} value={page.page_number}>
                          {page.page_number}
                        </option>
                      ))}
                    </select>
                    <span className="inline-meta" style={{ gap: 14 }}>
                      <span>
                        Words: <strong>{currentPageResult.words.length}</strong>
                      </span>
                      <span>
                        Avg. confidence: <strong>{formatConfidence(averageConfidence(currentPageResult.words))}</strong>
                      </span>
                      <span>
                        Page duration: <strong>{formatDuration(currentPageResult.duration_ms)}</strong>
                      </span>
                    </span>
                  </div>
                  <div className="ocr-text-block">{currentPageResult.text || '(no text recognized on this page)'}</div>
                </>
              )}
            </div>
          </div>
        )}

        {job.status === 'queued' && (
          <div className="card card-pad">
            <LoadingRow label="Waiting for a worker to pick up this job…" />
          </div>
        )}
        {job.status === 'running' && engines.length === 0 && (
          <div className="card card-pad">
            <LoadingRow label="Recognizing pages…" />
          </div>
        )}
      </div>

      {showCancelConfirm && (
        <ConfirmModal
          title="Cancel benchmark"
          description={
            cancelMutation.isError
              ? cancelMutation.error instanceof ApiError
                ? cancelMutation.error.message
                : 'Could not cancel this benchmark.'
              : 'Queued work stops immediately; a running job stops at the next page boundary.'
          }
          confirmLabel="Cancel benchmark"
          destructive
          pending={cancelMutation.isPending}
          onCancel={() => setShowCancelConfirm(false)}
          onConfirm={() => cancelMutation.mutate()}
        />
      )}
    </>
  )
}
