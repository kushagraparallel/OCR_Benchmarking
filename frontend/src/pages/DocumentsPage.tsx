import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteDocument, listDocuments, uploadDocument } from '../api/documents'
import { Alert } from '../components/Alert'
import { BenchmarkEngineModal } from '../components/BenchmarkEngineModal'
import { ConfirmModal } from '../components/ConfirmModal'
import { EmptyState } from '../components/EmptyState'
import { FileDropzone } from '../components/FileDropzone'
import { PageHeader } from '../components/PageHeader'
import { LoadingRow } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { DocumentIcon, FlaskIcon, TrashIcon } from '../components/icons'
import { ApiError } from '../lib/apiClient'
import { formatBytes, formatDateTime } from '../lib/format'
import type { DocumentSummary } from '../lib/types'

export function DocumentsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const documentsQuery = useQuery({ queryKey: ['documents'], queryFn: () => listDocuments(50, 0) })

  const [uploadError, setUploadError] = useState<string | null>(null)
  const [benchmarkTarget, setBenchmarkTarget] = useState<DocumentSummary | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DocumentSummary | null>(null)

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => {
      setUploadError(null)
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (err) => {
      setUploadError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      setDeleteTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const documents = documentsQuery.data?.items ?? []

  return (
    <>
      <PageHeader title="Documents" subtitle="Upload PDFs and launch OCR benchmarks against them." />
      <div className="page-content">
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-pad">
            <FileDropzone
              disabled={uploadMutation.isPending}
              onFileSelected={(file) => uploadMutation.mutate(file)}
            />
            {uploadMutation.isPending && (
              <div style={{ marginTop: 14 }}>
                <LoadingRow label="Uploading and validating PDF…" />
              </div>
            )}
            {uploadError && (
              <div style={{ marginTop: 14 }}>
                <Alert message={uploadError} />
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <h3>Your documents</h3>
              <div className="card-header-sub">{documents.length} uploaded</div>
            </div>
          </div>

          {documentsQuery.isLoading && (
            <div className="card-pad">
              <LoadingRow label="Loading documents…" />
            </div>
          )}

          {documentsQuery.isError && (
            <div className="card-pad">
              <Alert message="Could not load your documents." />
            </div>
          )}

          {documentsQuery.data && documents.length === 0 && (
            <EmptyState
              icon={<DocumentIcon width={28} height={28} />}
              title="No documents yet"
              description="Upload a PDF above to start comparing OCR engines on it."
            />
          )}

          {documents.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Pages</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td>
                      <div className="cell-primary">{document.original_filename}</div>
                      {document.pdf_title && <div className="cell-muted">{document.pdf_title}</div>}
                    </td>
                    <td className="cell-muted">{document.page_count}</td>
                    <td className="cell-muted">{formatBytes(document.size_bytes)}</td>
                    <td>
                      <StatusBadge status={document.status} />
                    </td>
                    <td className="cell-muted">{formatDateTime(document.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => setBenchmarkTarget(document)}>
                          <FlaskIcon width={13} height={13} />
                          Benchmark
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          aria-label={`Delete ${document.original_filename}`}
                          onClick={() => setDeleteTarget(document)}
                        >
                          <TrashIcon width={13} height={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {benchmarkTarget && (
        <BenchmarkEngineModal
          documentId={benchmarkTarget.id}
          documentName={benchmarkTarget.original_filename}
          onClose={() => setBenchmarkTarget(null)}
          onSubmitted={(jobId) => {
            setBenchmarkTarget(null)
            navigate(`/benchmarks/${jobId}`)
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmModal
          title="Delete document"
          description={`This permanently deletes "${deleteTarget.original_filename}" and its stored file. Existing benchmark results referencing it are kept.`}
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </>
  )
}
