import { useEffect, useRef, useState } from 'react'
import { Trash2, X } from 'lucide-react'

type UndoDeleteToastProps = {
  // How long the undo window stays open before the delete commits.
  durationMs?: number
  // Undo the delete — the row is restored, nothing hits the server.
  onUndo: () => void
  // Commit the delete — fired when the countdown elapses OR the user dismisses
  // the toast (which confirms immediately rather than waiting it out).
  onCommit: () => void
}

// Bottom-center countdown pill for a just-deleted memory. Mount it keyed on the
// pending memory id so each delete gets a fresh countdown. The toast owns the
// timer and reports back via onUndo / onCommit; the page owns what those do.
export function UndoDeleteToast({
  durationMs = 5000,
  onUndo,
  onCommit
}: UndoDeleteToastProps): React.JSX.Element {
  const [remaining, setRemaining] = useState(durationMs)
  // Keep the latest onCommit without resubscribing the interval each render (a
  // new onCommit identity per parent render must not reset the countdown).
  const commitRef = useRef(onCommit)
  useEffect(() => {
    commitRef.current = onCommit
  })

  useEffect(() => {
    const start = Date.now()
    const id = setInterval(() => {
      const left = durationMs - (Date.now() - start)
      if (left <= 0) {
        clearInterval(id)
        setRemaining(0)
        commitRef.current()
      } else {
        setRemaining(left)
      }
    }, 100)
    return () => clearInterval(id)
  }, [durationMs])

  const seconds = Math.ceil(remaining / 1000)

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[130] flex justify-center px-6">
      <div className="animate-fade-in pointer-events-auto flex items-center gap-3 rounded-full border border-white/10 bg-[var(--bg-secondary)] py-2.5 pl-4 pr-2.5 shadow-[0_12px_32px_rgba(0,0,0,0.5)]">
        <Trash2 className="h-4 w-4 text-white/50" aria-hidden />
        <span className="text-sm text-white/80">Memory deleted</span>
        <span className="w-6 text-center font-mono text-xs tabular-nums text-white/40">
          {seconds}s
        </span>
        <button
          type="button"
          onClick={onUndo}
          className="rounded-full px-3 py-1 text-sm font-medium text-white transition-colors hover:bg-white/10"
        >
          Undo
        </button>
        <button
          type="button"
          onClick={onCommit}
          className="rounded-full p-1.5 text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
          aria-label="Dismiss and delete now"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
