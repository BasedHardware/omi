import { useState } from 'react'
import { Loader2, Merge } from 'lucide-react'
import { ModalShell } from './ModalShell'

// Confirm a multi-select merge. Copy matches the Mac alert verbatim. Merge is
// fire-and-forget on the backend (returns {status:'merging'}, no new id) — the
// caller refetches the list after onConfirm resolves.
export function MergeConfirmDialog({
  count,
  onCancel,
  onConfirm
}: {
  count: number
  onCancel: () => void
  onConfirm: () => Promise<void>
}): React.JSX.Element {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (e) {
      setError((e as Error).message || 'Could not merge conversations')
      setBusy(false)
    }
  }

  return (
    <ModalShell onClose={onCancel} labelledBy="merge-title">
      <h2 id="merge-title" className="text-lg font-semibold text-text-primary">
        Merge {count} conversations?
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-text-tertiary">
        This will combine them into a single conversation and delete the originals. This action
        cannot be undone.
      </p>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onCancel} disabled={busy} className="btn-ghost">
          Cancel
        </button>
        <button onClick={() => void confirm()} disabled={busy} className="btn-primary">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Merge className="h-4 w-4" />}
          Merge
        </button>
      </div>
    </ModalShell>
  )
}
