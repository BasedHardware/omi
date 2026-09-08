import { useEffect, useRef, useState } from 'react'
import { Sparkles, Pencil, Trash2, Loader2, Plus, X, Check, NotebookPen } from 'lucide-react'
import { liveNotesMonitor } from '../../lib/liveNotes/liveNotesMonitor'
import { Toggle } from '../settings/Toggle'
import type { LiveNote } from '../../../../shared/types'

// PR8 LiveNotes panel — the right pane of the live-conversation split. Renders the
// running list of AI-generated + user-typed notes and lets the user add/edit/
// delete a typed note. Ports the macOS LiveNotesView (MainWindow/Components/
// LiveNotesView.swift) as clean Windows-native components (not cloned SwiftUI).
//
// PURPLE — on the record (INV-UI-1): Mac renders the AI accent (sparkles icon, add
// button) in `OmiColors.purplePrimary`. Ported here per the program's binding UI
// ruling — "match Mac's brand INCLUDING purple where Mac renders purple, in a
// CONTAINED module (not a global token)" — and CONFIRMED by the PR8 audit (keep it,
// do not flip to neutral). This is ONE contained constant, not a design token; the
// Windows brand ratchet (check_brand_ui.py) does not scan desktop/windows. If brand
// policy ever changes, revert is one line: AI_ACCENT = 'text-white'.
const AI_ACCENT = 'text-purple-400'

function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function NoteRow({ note }: { note: LiveNote }): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(note.text)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const startEdit = (): void => {
    setEditText(note.text)
    setEditing(true)
  }
  const commit = (): void => {
    const trimmed = editText.trim()
    if (trimmed && trimmed !== note.text) void liveNotesMonitor.updateNote(note.id, trimmed)
    setEditing(false)
  }
  const cancel = (): void => setEditing(false)

  return (
    <li className="group flex gap-2.5 rounded-lg px-2.5 py-2 hover:bg-white/[0.04]">
      {note.isAi ? (
        <Sparkles className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${AI_ACCENT}`} />
      ) : (
        <Pencil className="mt-0.5 h-3.5 w-3.5 shrink-0 text-white/40" />
      )}
      <div className="min-w-0 flex-1">
        {editing ? (
          <input
            ref={inputRef}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commit()
              else if (e.key === 'Escape') cancel()
            }}
            className="w-full rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-sm text-white/90 outline-none focus:border-white/30"
          />
        ) : (
          <p
            onDoubleClick={startEdit}
            className="cursor-text whitespace-pre-wrap break-words text-sm leading-snug text-white/85"
          >
            {note.text}
          </p>
        )}
        <span className="mt-0.5 block text-[10px] text-white/35">{formatTime(note.createdAt)}</span>
      </div>
      <div className="flex shrink-0 items-start gap-1">
        {editing ? (
          <>
            <button
              onClick={commit}
              title="Save"
              className="text-emerald-400 hover:text-emerald-300"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button onClick={cancel} title="Cancel" className="text-white/40 hover:text-white/70">
              <X className="h-3.5 w-3.5" />
            </button>
          </>
        ) : (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button onClick={startEdit} title="Edit" className="text-white/40 hover:text-white/80">
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => void liveNotesMonitor.deleteNote(note.id)}
              title="Delete"
              className="text-white/40 hover:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </li>
  )
}

export function LiveNotesPanel(): React.JSX.Element {
  const [notes, setNotes] = useState<LiveNote[]>(liveNotesMonitor.getNotes())
  const [generating, setGenerating] = useState(liveNotesMonitor.isGenerating())
  const [aiEnabled, setAiEnabled] = useState(liveNotesMonitor.isAiEnabled())
  const [draft, setDraft] = useState('')
  const listEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    return liveNotesMonitor.subscribe(() => {
      setNotes([...liveNotesMonitor.getNotes()])
      setGenerating(liveNotesMonitor.isGenerating())
      setAiEnabled(liveNotesMonitor.isAiEnabled())
    })
  }, [])

  // Auto-scroll to the newest note as the list grows.
  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [notes.length])

  const addNote = (): void => {
    const text = draft.trim()
    if (!text) return
    void liveNotesMonitor.addManualNote(text)
    setDraft('')
  }

  return (
    <div className="surface-card flex h-full min-h-[24rem] flex-col p-0">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="section-label">Notes</h2>
        <div className="flex items-center gap-2.5">
          <Sparkles className={`h-3.5 w-3.5 ${aiEnabled ? AI_ACCENT : 'text-white/30'}`} />
          <Toggle
            on={aiEnabled}
            onChange={(v) => liveNotesMonitor.setAiEnabled(v)}
            label="AI notes"
          />
          {generating && <Loader2 className="h-3.5 w-3.5 animate-spin text-white/45" />}
        </div>
      </div>
      <div className="h-px bg-white/10" />

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {notes.length > 0 ? (
          <ul className="space-y-0.5">
            {notes.map((n) => (
              <NoteRow key={n.id} note={n} />
            ))}
            <div ref={listEndRef} />
          </ul>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
            <NotebookPen className="h-7 w-7 text-white/25" />
            <p className="text-sm text-white/45">Notes will appear here</p>
            {aiEnabled && <p className="text-xs text-white/30">AI generates notes as you speak</p>}
          </div>
        )}
      </div>

      <div className="h-px bg-white/10" />
      <div className="flex items-center gap-2 px-3 py-2.5">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') addNote()
          }}
          placeholder="Add a note…"
          className="min-w-0 flex-1 bg-transparent text-sm text-white/85 placeholder:text-white/35 outline-none"
        />
        <button
          onClick={addNote}
          disabled={!draft.trim()}
          title="Add note"
          className={`shrink-0 transition-colors ${draft.trim() ? `${AI_ACCENT} hover:brightness-125` : 'text-white/25'}`}
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
