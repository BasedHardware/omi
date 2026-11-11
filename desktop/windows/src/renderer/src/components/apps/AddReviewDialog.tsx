import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Star, Loader2 } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import type { AppReview } from '../../lib/omiApi.generated'

const MAX_REVIEW_LEN = 500

type AddReviewDialogProps = {
  appId: string
  // The user's existing review, if any. When present the dialog is in edit mode
  // (title/button read "Edit") and pre-fills the star + text. Its absence means a
  // fresh review. Either way the write is the same POST upsert (macOS never PATCHes).
  existingReview: AppReview | null
  onClose: () => void
  // Called after a successful write with the submitted values so the parent can
  // optimistically render then re-fetch. The dialog never decodes a review from the
  // response body (the backend returns `{status:'ok'}`, NOT an AppReview).
  onSubmitted: (values: { score: number; review: string }) => void
}

// Read-only-ish star picker (1-5). Filled stars are amber/white — never purple
// (INV-UI-1). Hovering previews the score; clicking commits it.
function StarPicker({
  score,
  onPick
}: {
  score: number
  onPick: (n: number) => void
}): React.JSX.Element {
  const [hover, setHover] = useState(0)
  const shown = hover || score
  return (
    <div className="flex items-center gap-1" onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onPick(n)}
          onMouseEnter={() => setHover(n)}
          aria-label={`${n} star${n > 1 ? 's' : ''}`}
          className="rounded p-0.5 transition-transform hover:scale-110"
        >
          <Star
            className={`h-6 w-6 ${n <= shown ? 'fill-amber-400 text-amber-400' : 'text-white/25'}`}
          />
        </button>
      ))}
    </div>
  )
}

// Add / edit an app review. ~400×500 Radix dialog nested inside AppDetailSheet.
// Submit = POST /v1/apps/review?app_id=… body {score, review} for BOTH new and edit
// (backend upsert). Valid = a chosen star AND non-empty text. Errors render inline
// so the user can retry without losing their draft.
export function AddReviewDialog({
  appId,
  existingReview,
  onClose,
  onSubmitted
}: AddReviewDialogProps): React.JSX.Element {
  const [score, setScore] = useState(existingReview?.score ?? 0)
  const [text, setText] = useState(existingReview?.review ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isEdit = existingReview != null
  const valid = score > 0 && text.trim().length > 0

  const submit = async (): Promise<void> => {
    if (!valid || submitting) return
    const review = text.trim()
    setSubmitting(true)
    setError(null)
    try {
      // app_id is a QUERY param (backend reads it there); body carries score+review.
      // Response is `{status:'ok'}` — deliberately NOT decoded as a review.
      await omiApi.post('/v1/apps/review', { score, review }, { params: { app_id: appId } })
      onSubmitted({ score, review })
    } catch {
      setError('Failed to submit review. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[110] bg-black/50 data-[state=open]:animate-modal-overlay-in" />
        <div className="pointer-events-none fixed inset-0 z-[110] flex items-center justify-center p-6">
          <Dialog.Content
            aria-describedby={undefined}
            className="pointer-events-auto flex max-h-[85vh] w-full max-w-[400px] flex-col rounded-[var(--radius-card)] border border-white/10 bg-[var(--bg-secondary)] shadow-[0_16px_48px_rgba(0,0,0,0.5)] data-[state=open]:animate-modal-in"
          >
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <Dialog.Title className="font-display font-semibold text-white/95">
                {isEdit ? 'Edit your review' : 'Add a review'}
              </Dialog.Title>
              <Dialog.Close
                className="rounded-md p-1.5 text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div className="space-y-2">
                <label className="text-xs font-medium text-white/60">Your rating</label>
                <StarPicker score={score} onPick={setScore} />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-white/60">Your review</label>
                <textarea
                  autoFocus
                  value={text}
                  onChange={(e) => setText(e.target.value.slice(0, MAX_REVIEW_LEN))}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                      e.preventDefault()
                      void submit()
                    }
                  }}
                  rows={4}
                  placeholder="Share what you think about this app…"
                  className="input-field resize-none text-sm"
                />
                <div className="text-right text-[11px] text-white/35">
                  {text.length}/{MAX_REVIEW_LEN}
                </div>
              </div>

              {error && <p className="text-xs text-error">{error}</p>}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-white/10 px-5 py-4">
              <button
                onClick={onClose}
                disabled={submitting}
                className="btn-ghost px-3 py-1.5 text-sm"
              >
                Cancel
              </button>
              <button
                onClick={() => void submit()}
                disabled={!valid || submitting}
                className="btn-primary px-4 py-1.5 text-sm disabled:opacity-40"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : isEdit ? (
                  'Update review'
                ) : (
                  'Submit review'
                )}
              </button>
            </div>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
