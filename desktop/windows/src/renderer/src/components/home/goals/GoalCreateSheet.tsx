import { useMemo, useState } from 'react'
import { dashboardIntelligence } from '../../../lib/intelligence/dashboardStore'
import { ModalShell } from '../../conversations/ModalShell'

// The Add-goal sheet (mac parity: CanonicalGoalCreateSheet). One occurrence id
// is minted per sheet instance and used as the Idempotency-Key, so a retried
// save after a network failure cannot create a second goal. Save requires a
// trimmed title and desired outcome; success criteria split one per line;
// an empty why-it-matters goes to the wire as null, not an empty string.

export function GoalCreateSheet({ onClose }: { onClose: () => void }): React.JSX.Element {
  const occurrenceId = useMemo(() => crypto.randomUUID().toLowerCase(), [])
  const [title, setTitle] = useState('')
  const [desiredOutcome, setDesiredOutcome] = useState('')
  const [whyItMatters, setWhyItMatters] = useState('')
  const [criteria, setCriteria] = useState('')
  const [saving, setSaving] = useState(false)

  const canSave = title.trim().length > 0 && desiredOutcome.trim().length > 0 && !saving

  const save = async (): Promise<void> => {
    if (!canSave) return
    setSaving(true)
    const why = whyItMatters.trim()
    const ok = await dashboardIntelligence.createGoal(
      {
        title: title.trim(),
        desiredOutcome: desiredOutcome.trim(),
        whyItMatters: why.length > 0 ? why : null,
        successCriteria: criteria
          .split('\n')
          .map((line) => line.trim())
          .filter((line) => line.length > 0)
      },
      occurrenceId
    )
    setSaving(false)
    if (ok) onClose()
  }

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-[460px]" labelledBy="goal-create-title-heading">
      <div>
        <h2 id="goal-create-title-heading" className="mb-4 text-[16px] font-semibold text-home-ink">
          Add goal
        </h2>
        <Field label="Short name">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-md border border-home-hairline bg-home-tile px-2 py-1.5 text-[13px] text-home-ink"
            data-testid="goal-create-title"
          />
        </Field>
        <Field label="Desired outcome">
          <textarea
            value={desiredOutcome}
            onChange={(e) => setDesiredOutcome(e.target.value)}
            rows={2}
            className="w-full resize-none rounded-md border border-home-hairline bg-home-tile px-2 py-1.5 text-[13px] text-home-ink"
            data-testid="goal-create-outcome"
          />
        </Field>
        <Field label="Why it matters (optional)">
          <textarea
            value={whyItMatters}
            onChange={(e) => setWhyItMatters(e.target.value)}
            rows={2}
            className="w-full resize-none rounded-md border border-home-hairline bg-home-tile px-2 py-1.5 text-[13px] text-home-ink"
          />
        </Field>
        <Field label="Success criteria, one per line">
          <textarea
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-home-hairline bg-home-tile px-2 py-1.5 text-[13px] text-home-ink"
          />
        </Field>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="focus-ring rounded-md border border-home-hairline px-3 py-1.5 text-[12px] font-medium text-home-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSave}
            onClick={() => void save()}
            className="focus-ring rounded-md bg-home-tileHover px-3 py-1.5 text-[12px] font-semibold text-home-ink disabled:opacity-40"
            data-testid="goal-create-save"
          >
            Add goal
          </button>
        </div>
      </div>
    </ModalShell>
  )
}

function Field({
  label,
  children
}: {
  label: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-[11px] font-medium text-home-muted">{label}</span>
      {children}
    </label>
  )
}
