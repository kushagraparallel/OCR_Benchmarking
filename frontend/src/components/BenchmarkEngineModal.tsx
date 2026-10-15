import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listAvailableEngines, submitBenchmark } from '../api/benchmarks'
import { ApiError } from '../lib/apiClient'
import { engineDisplayName } from '../lib/format'
import { Alert } from './Alert'
import { LoadingRow, Spinner } from './Spinner'

interface BenchmarkEngineModalProps {
  documentId: string
  documentName: string
  onClose: () => void
  onSubmitted: (jobId: string) => void
}

export function BenchmarkEngineModal({ documentId, documentName, onClose, onSubmitted }: BenchmarkEngineModalProps) {
  const enginesQuery = useQuery({ queryKey: ['engines'], queryFn: listAvailableEngines })
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  function toggle(engine: string) {
    setSelected((current) =>
      current.includes(engine) ? current.filter((name) => name !== engine) : [...current, engine],
    )
  }

  async function handleSubmit() {
    if (selected.length === 0) {
      setError('Select at least one OCR engine.')
      return
    }
    setError(null)
    setIsSubmitting(true)
    try {
      const job = await submitBenchmark(documentId, selected)
      onSubmitted(job.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not queue the benchmark.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <h3>Run a benchmark</h3>
        <p className="modal-card-sub">
          Compare OCR engines on <strong>{documentName}</strong>. Up to 4 engines per run.
        </p>

        {error && (
          <div style={{ marginBottom: 12 }}>
            <Alert message={error} />
          </div>
        )}

        {enginesQuery.isLoading && <LoadingRow label="Loading available engines…" />}
        {enginesQuery.isError && <Alert message="Could not load the available OCR engines." />}

        {enginesQuery.data && enginesQuery.data.length === 0 && (
          <Alert variant="info" message="No OCR engines are enabled on this deployment yet." />
        )}

        {enginesQuery.data && enginesQuery.data.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {enginesQuery.data.map((engine) => (
              <label key={engine} className="checkbox-row">
                <input
                  type="checkbox"
                  checked={selected.includes(engine)}
                  disabled={!selected.includes(engine) && selected.length >= 4}
                  onChange={() => toggle(engine)}
                />
                {engineDisplayName(engine)}
              </label>
            ))}
          </div>
        )}

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </button>
          <button
            className="btn btn-accent"
            onClick={() => void handleSubmit()}
            disabled={isSubmitting || enginesQuery.isLoading || !enginesQuery.data?.length}
          >
            {isSubmitting && <Spinner light />}
            Queue benchmark
          </button>
        </div>
      </div>
    </div>
  )
}
