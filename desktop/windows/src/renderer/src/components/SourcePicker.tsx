import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import type { CaptureSource } from '../../../shared/types'

export function SourcePicker(props: {
  open: boolean
  onClose: () => void
  onPick: (s: CaptureSource) => void
}): React.JSX.Element | null {
  const [sources, setSources] = useState<CaptureSource[]>([])

  useEffect(() => {
    if (!props.open) return
    window.omi.getCaptureSources().then(setSources).catch(() => setSources([]))
  }, [props.open])

  if (!props.open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-primary/40 p-6 backdrop-blur-md"
      onClick={props.onClose}
    >
      <div
        className="glass max-h-[80vh] w-full max-w-[720px] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <h3 className="font-display text-xl font-bold text-text-primary">
            Choose a window or screen
          </h3>
          <button
            onClick={props.onClose}
            className="rounded-xl border border-white/10 bg-white/5 p-2 text-text-tertiary backdrop-blur-sm transition-colors hover:bg-white/10 hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {sources.length === 0 && (
          <div className="py-12 text-center text-sm text-text-tertiary">Loading sources…</div>
        )}
        <div className="grid grid-cols-3 gap-3">
          {sources.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                props.onPick(s)
                props.onClose()
              }}
              className="surface-card-interactive overflow-hidden p-2 text-left"
            >
              <img
                src={s.thumbnailDataUrl}
                alt={s.name}
                className="w-full rounded-xl border border-white/10"
              />
              <div className="mt-2 truncate text-xs text-text-secondary">{s.name}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
