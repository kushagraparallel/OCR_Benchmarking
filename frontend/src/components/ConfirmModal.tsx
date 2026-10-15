import { Spinner } from './Spinner'

interface ConfirmModalProps {
  title: string
  description: string
  confirmLabel?: string
  destructive?: boolean
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  title,
  description,
  confirmLabel = 'Confirm',
  destructive = false,
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <h3>{title}</h3>
        <p className="modal-card-sub">{description}</p>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </button>
          <button className={`btn ${destructive ? 'btn-danger' : 'btn-accent'}`} onClick={onConfirm} disabled={pending}>
            {pending && <Spinner />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
