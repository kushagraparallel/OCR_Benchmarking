import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listBenchmarks } from '../api/benchmarks'
import { listDocuments } from '../api/documents'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { LoadingRow } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { Alert } from '../components/Alert'
import { FlaskIcon } from '../components/icons'
import { engineDisplayName, formatDateTime, formatDuration } from '../lib/format'
import type { BenchmarkJob } from '../lib/types'

const ACTIVE_STATUSES = new Set(['queued', 'running', 'cancellation_requested'])

export function BenchmarksPage() {
  const navigate = useNavigate()

  const benchmarksQuery = useQuery({
    queryKey: ['benchmarks'],
    queryFn: () => listBenchmarks(50, 0),
    refetchInterval: (query) => {
      const jobs = query.state.data?.items ?? []
      return jobs.some((job) => ACTIVE_STATUSES.has(job.status)) ? 3000 : false
    },
  })

  const documentsQuery = useQuery({ queryKey: ['documents'], queryFn: () => listDocuments(50, 0) })
  const documentNameById = new Map(documentsQuery.data?.items.map((doc) => [doc.id, doc.original_filename]) ?? [])

  const jobs = benchmarksQuery.data?.items ?? []

  return (
    <>
      <PageHeader title="Benchmarks" subtitle="Track queued, running, and completed OCR engine comparisons." />
      <div className="page-content">
        <div className="card">
          <div className="card-header">
            <div>
              <h3>Job history</h3>
              <div className="card-header-sub">{jobs.length} total</div>
            </div>
          </div>

          {benchmarksQuery.isLoading && (
            <div className="card-pad">
              <LoadingRow label="Loading benchmark jobs…" />
            </div>
          )}

          {benchmarksQuery.isError && (
            <div className="card-pad">
              <Alert message="Could not load benchmark jobs." />
            </div>
          )}

          {benchmarksQuery.data && jobs.length === 0 && (
            <EmptyState
              icon={<FlaskIcon width={28} height={28} />}
              title="No benchmarks yet"
              description="Upload a document and run a benchmark to see results here."
            />
          )}

          {jobs.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Document</th>
                  <th>Engines</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job: BenchmarkJob) => (
                  <tr key={job.id} className="is-clickable" onClick={() => navigate(`/benchmarks/${job.id}`)}>
                    <td className="cell-id">{job.id.slice(0, 8)}</td>
                    <td className="cell-primary">{documentNameById.get(job.document_id) ?? job.document_id.slice(0, 8)}</td>
                    <td className="cell-muted">{job.engine_names.map(engineDisplayName).join(', ')}</td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="cell-muted">{formatDateTime(job.created_at)}</td>
                    <td className="cell-muted">{job.result ? formatDuration(job.result.duration_ms) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
