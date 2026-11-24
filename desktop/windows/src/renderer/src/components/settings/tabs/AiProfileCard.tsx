// Settings → Advanced → "AI profile" subsection. Mac parity with
// aiUserProfileSubsection (SettingsContentView): shows the synthesized "about you"
// profile with its last-updated date + data-source count, and lets the user
// Regenerate, inline-Edit (Save), or Delete it. The backend owns the profile
// (generation, daily cadence, storage); this UI is a thin driver over the
// aiProfile:* IPCs, which proxy GET / POST refresh / PATCH / DELETE on
// /v1/users/ai-profile.
//
// There is deliberately NO enable toggle here — the backend generates for every
// user, so this is preview/CRUD only.
import { useEffect, useState } from 'react'
import { UserRound } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import type { AiUserProfile } from '../../../../../shared/types'
import {
  AI_PROFILE_FALLBACK as FALLBACK,
  aiProfileErrorMessage
} from '../../../lib/aiProfileMessages'

export function AiProfileCard(): React.JSX.Element {
  const [record, setRecord] = useState<AiUserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Inline edit state.
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const [confirmingDelete, setConfirmingDelete] = useState(false)

  useEffect(() => {
    void window.omi
      .aiProfileGet()
      .then((r) => {
        if (r.ok) {
          setRecord(r.value)
        } else {
          setRecord(null)
          setError(aiProfileErrorMessage(r.code, 'load'))
        }
      })
      .catch(() => setRecord(null))
      .finally(() => setLoading(false))
  }, [])

  const regenerate = async (): Promise<void> => {
    if (generating) return
    setGenerating(true)
    setError(null)
    try {
      // The backend synthesizes synchronously (~10-40 s).
      const r = await window.omi.aiProfileRefresh()
      if (r.ok) {
        setRecord(r.value)
        setEditing(false)
      } else {
        setError(aiProfileErrorMessage(r.code, 'generate'))
      }
    } catch {
      setError(FALLBACK.generate)
    } finally {
      setGenerating(false)
    }
  }

  const startEdit = (): void => {
    if (!record) return
    setDraft(record.profileText)
    setEditing(true)
    setError(null)
  }

  const saveEdit = async (): Promise<void> => {
    if (!record || saving) return
    setSaving(true)
    setError(null)
    try {
      const r = await window.omi.aiProfileEdit(draft)
      if (r.ok) {
        // The backend's copy is the source of truth after the write.
        setRecord(r.value)
        setEditing(false)
      } else {
        setError(aiProfileErrorMessage(r.code, 'save'))
      }
    } catch {
      setError(FALLBACK.save)
    } finally {
      setSaving(false)
    }
  }

  const remove = async (): Promise<void> => {
    if (!record) return
    setError(null)
    try {
      const r = await window.omi.aiProfileDelete()
      if (r.ok) setRecord(null)
      else setError(aiProfileErrorMessage(r.code, 'delete'))
    } catch {
      setError(FALLBACK.delete)
    } finally {
      setConfirmingDelete(false)
    }
  }

  const updatedAt = record ? (record.generatedAt ?? record.refreshedAt) : null

  return (
    <SettingRow
      icon={UserRound}
      title="AI profile"
      subtitle="A synthesized “about you” summary Omi builds from your memories, tasks, goals, and conversations — used to personalize proactive help."
      keywords="ai profile about you dossier synthesized personalize regenerate"
    >
      <div className="space-y-3">
        {loading ? (
          <p className="text-sm text-text-tertiary">Loading…</p>
        ) : !record ? (
          // Empty state.
          <div className="space-y-3">
            <p className="text-sm text-text-tertiary">No profile yet.</p>
            <button
              onClick={regenerate}
              disabled={generating}
              className="btn-primary px-4 py-2 disabled:opacity-40"
            >
              {generating ? 'Generating…' : 'Generate Now'}
            </button>
          </div>
        ) : editing ? (
          // Inline edit.
          <div className="space-y-3">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={8}
              className="input-field resize-none"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={saveEdit}
                disabled={saving}
                className="btn-primary px-4 py-2 disabled:opacity-40"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  setError(null)
                }}
                disabled={saving}
                className="btn-ghost disabled:opacity-40"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          // Preview.
          <div className="space-y-3">
            <div className="glass-subtle max-h-56 select-text overflow-y-auto whitespace-pre-wrap rounded-lg px-4 py-3 text-sm text-text-secondary">
              {record.profileText}
            </div>
            <p className="text-xs text-text-tertiary">
              {updatedAt !== null && (
                <>Last updated: {new Date(updatedAt).toLocaleDateString()} · </>
              )}
              Data sources: {record.dataSourcesUsed}{' '}
              {record.dataSourcesUsed === 1 ? 'item' : 'items'}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={regenerate}
                disabled={generating}
                className="btn-ghost disabled:opacity-40"
              >
                {generating ? 'Regenerating…' : 'Regenerate'}
              </button>
              <button
                onClick={startEdit}
                disabled={generating}
                className="btn-ghost disabled:opacity-40"
              >
                Edit
              </button>
              {confirmingDelete ? (
                <>
                  <button
                    onClick={remove}
                    className="text-sm font-medium text-red-400 hover:text-red-300"
                  >
                    Confirm delete
                  </button>
                  <button
                    onClick={() => setConfirmingDelete(false)}
                    className="btn-ghost disabled:opacity-40"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setConfirmingDelete(true)}
                  disabled={generating}
                  className="text-sm font-medium text-red-400 hover:text-red-300 disabled:opacity-40"
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-amber-400">{error}</p>}
      </div>
    </SettingRow>
  )
}
