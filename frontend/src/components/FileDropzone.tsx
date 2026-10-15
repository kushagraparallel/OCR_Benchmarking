import { useRef, useState, type DragEvent } from 'react'
import { UploadIcon } from './icons'

interface FileDropzoneProps {
  onFileSelected: (file: File) => void
  disabled?: boolean
  accept?: string
}

export function FileDropzone({ onFileSelected, disabled = false, accept = 'application/pdf' }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isActive, setIsActive] = useState(false)

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsActive(false)
    if (disabled) return
    const file = event.dataTransfer.files[0]
    if (file) onFileSelected(file)
  }

  return (
    <div
      className={`dropzone${isActive ? ' is-active' : ''}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setIsActive(true)
      }}
      onDragLeave={() => setIsActive(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="visually-hidden"
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFileSelected(file)
          event.target.value = ''
        }}
      />
      <UploadIcon width={22} height={22} style={{ color: 'var(--ink-500)' }} />
      <h4 style={{ marginTop: 10 }}>Drop a PDF here or click to browse</h4>
      <p>Up to 25 MB, 100 pages. Only PDF documents are accepted.</p>
    </div>
  )
}
