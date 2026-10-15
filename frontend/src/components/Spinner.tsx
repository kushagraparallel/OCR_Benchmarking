export function Spinner({ light = false }: { light?: boolean }) {
  return <span className={`spinner${light ? ' spinner-light' : ''}`} aria-hidden="true" />
}

export function LoadingRow({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading-row">
      <Spinner />
      <span>{label}</span>
    </div>
  )
}
