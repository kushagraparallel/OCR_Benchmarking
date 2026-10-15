export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffSeconds = Math.round(diffMs / 1000)
  if (diffSeconds < 5) return 'just now'
  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.round(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(2)} s`
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return `${minutes}m ${remaining}s`
}

// Engine adapters normalize confidence to a shared 0–100 scale (see backend/app/core/ocr/README.md).
export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return '—'
  return `${Math.round(confidence)}%`
}

export function averageConfidence(words: { confidence: number | null }[]): number | null {
  const scored = words.filter((word): word is { confidence: number } => word.confidence !== null)
  if (scored.length === 0) return null
  return scored.reduce((sum, word) => sum + word.confidence, 0) / scored.length
}

export function engineDisplayName(name: string): string {
  const overrides: Record<string, string> = {
    tesseract: 'Tesseract',
    easyocr: 'EasyOCR',
    paddleocr: 'PaddleOCR',
    doctr: 'docTR',
  }
  return overrides[name] ?? name
}
