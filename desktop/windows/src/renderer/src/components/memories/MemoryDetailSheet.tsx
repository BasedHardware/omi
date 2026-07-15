import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Trash2, Pencil, ArrowUpRight, Loader2 } from 'lucide-react'
import type { Memory } from '../../hooks/useMemories'
import {
  CATEGORY_LABEL,
  categoryOf,
  formatMemoryDate,
  isProtectedContent,
  layerLabel
} from '../../lib/memoryFilters'
import { Badge } from '../ui/Badge'
import { Toggle } from '../ui/Toggle'

type MemoryDetailSheetProps = {
  // The memory being viewed; null closes the sheet.
  memory: Memory | null
  onClose: () => void
  onEdit: (id: string, content: string) => Promise<void>
  onToggleVisibility: (m: Memory) => Promise<void>
  onDelete: (m: Memory) => void
  onOpenConversation: (conversationId: string) => void
  togglingVisibility: boolean
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex gap-3 py-1.5 text-sm">
      <span className="w-28 shrink-0 text-white/40">{label}</span>
      <span className="min-w-0 flex-1 text-white/80">{value}</span>
    </div>
  )
}

// ~450×600 detail sheet for a single memory: public/private toggle, click-to-edit
// content, a metadata panel, and a link to the source conversation. Built on
// Radix Dialog (scrim, focus-trap, Esc/outside dismiss) so it matches the app's
// Modal chrome without inheriting Modal's fixed title/padding layout.
export function MemoryDetailSheet({
  memory,
  onClose,
  onEdit,
  onToggleVisibility,
  onDelete,
  onOpenConversation,
  togglingVisibility
}: MemoryDetailSheetProps): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  // Reset edit state whenever the viewed memory changes (or the sheet reopens).
  useEffect(() => {
    setEditing(false)
    setDraft(memory?.content ?? '')
    setSaving(false)
  }, [memory])

  if (!memory) return <></>

  const protectedMem = isProtectedContent(memory.content)
  const layer = layerLabel(memory)
  const isPublic = memory.visibility === 'public'

  const saveEdit = async (): Promise<void> => {
    const text = draft.trim()
    if (!text || saving) return
    setSaving(true)
    try {
      await onEdit(memory.id, text)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/50 data-[state=open]:animate-modal-overlay-in" />
        <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center p-6">
          <Dialog.Content
            aria-describedby={undefined}
            className="pointer-events-auto flex max-h-[85vh] w-full max-w-[450px] flex-col rounded-[var(--radius-card)] border border-white/10 bg-[var(--bg-secondary)] shadow-[0_16px_48px_rgba(0,0,0,0.5)] data-[state=open]:animate-modal-in"
          >
            <Dialog.Title className="sr-only">Memory details</Dialog.Title>

            {/* Header: category + tier, then visibility toggle, delete, dismiss. */}
            <div className="flex items-center gap-2 border-b border-white/10 px-5 py-4">
              <Badge tone="neutral" size="sm">
                {CATEGORY_LABEL[categoryOf(memory)]}
              </Badge>
              {layer && (
                <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[11px] text-white/60">
                  {layer}
                </span>
              )}
              <div className="ml-auto flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-white/60">
                  <span>{isPublic ? 'Public' : 'Private'}</span>
                  <Toggle
                    checked={isPublic}
                    disabled={togglingVisibility}
                    onChange={() => void onToggleVisibility(memory)}
                    ariaLabel="Toggle public visibility"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => onDelete(memory)}
                  className="rounded-md p-1.5 text-white/40 transition-colors hover:bg-white/5 hover:text-error"
                  aria-label="Delete memory"
                  title="Delete memory"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <Dialog.Close
                  className="rounded-md p-1.5 text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" />
                </Dialog.Close>
              </div>
            </div>

            {/* Body */}
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {editing ? (
                <div className="space-y-2">
                  <textarea
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                        e.preventDefault()
                        void saveEdit()
                      } else if (e.key === 'Escape') {
                        e.stopPropagation()
                        setEditing(false)
                        setDraft(memory.content)
                      }
                    }}
                    rows={4}
                    className="input-field resize-none text-sm"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => {
                        setEditing(false)
                        setDraft(memory.content)
                      }}
                      disabled={saving}
                      className="btn-ghost px-3 py-1.5 text-sm"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => void saveEdit()}
                      disabled={saving || !draft.trim()}
                      className="btn-primary px-3 py-1.5 text-sm disabled:opacity-40"
                    >
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                    </button>
                  </div>
                </div>
              ) : protectedMem ? (
                <p className="italic text-white/40">Protected memory</p>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setDraft(memory.content)
                    setEditing(true)
                  }}
                  className="group flex w-full items-start gap-2 text-left text-[15px] leading-relaxed text-white/90"
                  title="Click to edit"
                >
                  <span className="flex-1">{memory.content}</span>
                  <Pencil className="mt-1 h-3.5 w-3.5 shrink-0 text-white/25 opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              )}

              {/* Metadata panel */}
              <div className="mt-5 rounded-xl bg-[var(--bg-tertiary)] px-4 py-2">
                {typeof memory.capture_confidence === 'number' && (
                  <MetaRow
                    label="Confidence"
                    value={`${Math.round(memory.capture_confidence * 100)}%`}
                  />
                )}
                {memory.app_id && <MetaRow label="Source app" value={memory.app_id} />}
                {memory.primary_capture_device && (
                  <MetaRow label="Device" value={memory.primary_capture_device} />
                )}
                <MetaRow label="Created" value={formatMemoryDate(memory.created_at)} />
                {(memory.tags ?? []).filter((t) => t && !t.startsWith('omi-')).length > 0 && (
                  <MetaRow
                    label="Tags"
                    value={
                      <span className="flex flex-wrap gap-1">
                        {(memory.tags ?? [])
                          .filter((t) => t && !t.startsWith('omi-'))
                          .map((t) => (
                            <span
                              key={t}
                              className="rounded bg-white/10 px-1.5 py-0.5 text-[11px] text-white/70"
                            >
                              {t}
                            </span>
                          ))}
                      </span>
                    }
                  />
                )}
              </div>

              {memory.conversation_id && (
                <button
                  type="button"
                  onClick={() => onOpenConversation(memory.conversation_id as string)}
                  className="mt-4 flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white/80 transition-colors hover:bg-white/[0.06]"
                >
                  <span>View source conversation</span>
                  <ArrowUpRight className="h-4 w-4 text-white/50" />
                </button>
              )}
            </div>
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
