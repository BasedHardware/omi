import { useEffect, useRef, useState } from 'react'
import { X, Plus, Loader2, User } from 'lucide-react'
import { cn } from '../../lib/utils'

export type Person = { id: string; name: string }

export type SpeakerTarget = {
  rawLabel: string
  previewText: string
  segmentCount: number // total segments with this speaker label
}

interface Props {
  target: SpeakerTarget
  people: Person[]
  onClose: () => void
  onSave: (personId: string | null, isUser: boolean, allSegments: boolean) => Promise<void>
  onCreatePerson: (name: string) => Promise<Person | null>
}

export function NameSpeakerSheet({ target, people, onClose, onSave, onCreatePerson }: Props): React.JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isUser, setIsUser] = useState(false)
  const [allSegments, setAllSegments] = useState(true)
  const [addingNew, setAddingNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [duplicateError, setDuplicateError] = useState(false)
  const newNameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (addingNew) newNameRef.current?.focus()
  }, [addingNew])

  const selectUser = (): void => {
    setIsUser(true)
    setSelectedId(null)
    setAddingNew(false)
  }

  const selectPerson = (id: string): void => {
    setIsUser(false)
    setSelectedId(id)
    setAddingNew(false)
  }

  const startAddNew = (): void => {
    setIsUser(false)
    setSelectedId(null)
    setAddingNew(true)
    setNewName('')
    setDuplicateError(false)
  }

  const commitNewPerson = async (): Promise<void> => {
    const name = newName.trim()
    if (!name) return
    if (people.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      setDuplicateError(true)
      return
    }
    setCreating(true)
    try {
      const p = await onCreatePerson(name)
      if (p) {
        setSelectedId(p.id)
        setAddingNew(false)
        setNewName('')
      }
    } finally {
      setCreating(false)
    }
  }

  const canSave = isUser || selectedId != null

  const save = async (): Promise<void> => {
    if (!canSave || saving) return
    setSaving(true)
    try {
      await onSave(selectedId, isUser, allSegments)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-strong w-[400px] max-w-[calc(100vw-2rem)] rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-white/[0.07] px-6 py-4">
          <User className="h-4 w-4 text-[color:var(--accent)]" strokeWidth={1.75} />
          <h2 className="flex-1 text-sm font-semibold text-white/90">Name Speaker</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-white/30 hover:bg-white/10 hover:text-white/70">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Speaker preview card */}
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-4 py-3">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-white/30">
              {target.rawLabel.replace(/^SPEAKER_0*/, 'Speaker ')}
            </p>
            <p className="line-clamp-2 text-sm text-white/60">
              "{target.previewText.slice(0, 120)}{target.previewText.length > 120 ? '…' : ''}"
            </p>
          </div>

          {/* Person selection */}
          <div>
            <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-white/35">Who is this?</p>
            <div className="flex flex-wrap gap-2">
              {/* You chip */}
              <button
                onClick={selectUser}
                className={cn(
                  'rounded-xl border px-3 py-1.5 text-sm font-medium transition-all',
                  isUser
                    ? 'border-[color:var(--accent)]/40 bg-[color:var(--accent)]/15 text-[color:var(--accent)]'
                    : 'border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]'
                )}
              >
                You
              </button>

              {/* Existing people */}
              {people.map((p) => (
                <button
                  key={p.id}
                  onClick={() => selectPerson(p.id)}
                  className={cn(
                    'rounded-xl border px-3 py-1.5 text-sm font-medium transition-all',
                    selectedId === p.id && !isUser
                      ? 'border-[color:var(--accent)]/40 bg-[color:var(--accent)]/15 text-[color:var(--accent)]'
                      : 'border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]'
                  )}
                >
                  {p.name}
                </button>
              ))}

              {/* Add new */}
              <button
                onClick={startAddNew}
                className={cn(
                  'flex items-center gap-1 rounded-xl border px-3 py-1.5 text-sm font-medium transition-all',
                  addingNew
                    ? 'border-white/20 bg-white/[0.08] text-white/80'
                    : 'border-white/10 bg-white/[0.04] text-white/45 hover:bg-white/[0.08]'
                )}
              >
                <Plus className="h-3.5 w-3.5" />
                Add Person
              </button>
            </div>

            {/* New person input */}
            {addingNew && (
              <div className="mt-3 flex items-center gap-2">
                <input
                  ref={newNameRef}
                  value={newName}
                  onChange={(e) => { setNewName(e.target.value); setDuplicateError(false) }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void commitNewPerson()
                    else if (e.key === 'Escape') setAddingNew(false)
                  }}
                  placeholder="Person name"
                  className="flex-1 rounded-xl border border-white/15 bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-white/30 focus:outline-none"
                />
                <button
                  onClick={() => void commitNewPerson()}
                  disabled={!newName.trim() || creating}
                  className="rounded-xl bg-[color:var(--accent)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Add'}
                </button>
              </div>
            )}
            {duplicateError && (
              <p className="mt-1 text-xs text-red-400">A person with that name already exists.</p>
            )}
          </div>

          {/* All segments toggle */}
          {target.segmentCount > 1 && (
            <label className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={allSegments}
                onChange={(e) => setAllSegments(e.target.checked)}
                className="h-4 w-4 rounded border-white/20 bg-white/10 accent-[color:var(--accent)]"
              />
              <span className="text-sm text-white/60">
                Also tag {target.segmentCount - 1} other segment{target.segmentCount > 2 ? 's' : ''} from this speaker
              </span>
            </label>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-white/[0.07] px-6 py-3">
          <button onClick={onClose} className="btn-ghost px-4 py-2 text-sm">Cancel</button>
          <button
            onClick={() => void save()}
            disabled={!canSave || saving}
            className="btn-primary px-5 py-2 text-sm disabled:opacity-40"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
