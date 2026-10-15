import { AlertIcon } from './icons'

export function Alert({ message, variant = 'error' }: { message: string; variant?: 'error' | 'info' }) {
  return (
    <div className={`alert alert-${variant}`} role={variant === 'error' ? 'alert' : undefined}>
      <AlertIcon width={16} height={16} />
      <span>{message}</span>
    </div>
  )
}
