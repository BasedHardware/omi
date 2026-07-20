import { X } from 'lucide-react'

export function SourcePicker(props: {
  open: boolean
  onClose: () => void
  onPick: () => Promise<void>
}): React.JSX.Element | null {
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
        <button
          onClick={() => {
            void props.onPick().finally(props.onClose)
          }}
          className="surface-card-interactive w-full p-4 text-left text-sm text-text-secondary"
        >
          Choose a window or screen
        </button>
      </div>
    </div>
  )
}
