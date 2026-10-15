const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  queued: { label: 'Queued', className: 'badge-neutral' },
  running: { label: 'Running', className: 'badge-blue' },
  cancellation_requested: { label: 'Cancelling', className: 'badge-amber' },
  cancelled: { label: 'Cancelled', className: 'badge-neutral' },
  completed: { label: 'Completed', className: 'badge-green' },
  success: { label: 'Success', className: 'badge-green' },
  partial: { label: 'Partial', className: 'badge-amber' },
  failed: { label: 'Failed', className: 'badge-red' },
  timed_out: { label: 'Timed out', className: 'badge-red' },
  uploaded: { label: 'Uploaded', className: 'badge-violet' },
}

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? { label: status, className: 'badge-neutral' }
  return (
    <span className={`badge ${style.className}`}>
      <span className="badge-dot" />
      {style.label}
    </span>
  )
}
