import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { listSessions, revokeSession } from '../api/sessions'
import { Alert } from '../components/Alert'
import { ConfirmModal } from '../components/ConfirmModal'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { LoadingRow } from '../components/Spinner'
import { ShieldIcon } from '../components/icons'
import { useAuth } from '../context/AuthContext'
import { getAccessToken } from '../lib/apiClient'
import { formatDateTime, formatRelative } from '../lib/format'
import { decodeAccessTokenClaims } from '../lib/jwt'
import type { SessionSummary } from '../lib/types'

export function SessionsPage() {
  const queryClient = useQueryClient()
  const { logoutAll } = useAuth()
  const [revokeTarget, setRevokeTarget] = useState<SessionSummary | null>(null)
  const [showSignOutAll, setShowSignOutAll] = useState(false)

  const sessionsQuery = useQuery({ queryKey: ['sessions'], queryFn: listSessions })

  const revokeMutation = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => {
      setRevokeTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const currentToken = getAccessToken()
  const currentSessionId = currentToken ? decodeAccessTokenClaims(currentToken)?.sid : null
  const sessions = sessionsQuery.data ?? []

  return (
    <>
      <PageHeader
        title="Sessions"
        subtitle="Devices and browsers currently signed in to your account."
        actions={
          sessions.length > 1 ? (
            <button className="btn btn-danger" onClick={() => setShowSignOutAll(true)}>
              Sign out all devices
            </button>
          ) : undefined
        }
      />
      <div className="page-content">
        <div className="card">
          <div className="card-header">
            <div>
              <h3>Active sessions</h3>
              <div className="card-header-sub">{sessions.length} active</div>
            </div>
          </div>

          {sessionsQuery.isLoading && (
            <div className="card-pad">
              <LoadingRow label="Loading sessions…" />
            </div>
          )}

          {sessionsQuery.isError && (
            <div className="card-pad">
              <Alert message="Could not load your sessions." />
            </div>
          )}

          {sessionsQuery.data && sessions.length === 0 && (
            <EmptyState icon={<ShieldIcon width={28} height={28} />} title="No active sessions" />
          )}

          {sessions.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Expires</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => {
                  const isCurrent = session.id === currentSessionId
                  return (
                    <tr key={session.id}>
                      <td>
                        <div className="cell-primary">{session.user_agent ?? 'Unknown device'}</div>
                        {isCurrent && (
                          <span className="badge badge-green" style={{ marginTop: 4 }}>
                            This device
                          </span>
                        )}
                      </td>
                      <td className="cell-muted">{formatDateTime(session.created_at)}</td>
                      <td className="cell-muted">
                        {session.last_used_at ? formatRelative(session.last_used_at) : 'Never'}
                      </td>
                      <td className="cell-muted">{formatDateTime(session.expires_at)}</td>
                      <td>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => setRevokeTarget(session)}>
                            Revoke
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {revokeTarget && (
        <ConfirmModal
          title="Revoke session"
          description={`Sign out "${revokeTarget.user_agent ?? 'this device'}"? It will need to sign in again.`}
          confirmLabel="Revoke"
          destructive
          pending={revokeMutation.isPending}
          onCancel={() => setRevokeTarget(null)}
          onConfirm={() => revokeMutation.mutate(revokeTarget.id)}
        />
      )}

      {showSignOutAll && (
        <ConfirmModal
          title="Sign out all devices"
          description="This revokes every active session, including this one. You will need to sign in again."
          confirmLabel="Sign out everywhere"
          destructive
          onCancel={() => setShowSignOutAll(false)}
          onConfirm={() => void logoutAll()}
        />
      )}
    </>
  )
}
