import { useEffect, useRef, useState } from 'react'
import { X, Plus, Trash2, Sparkles, Loader2, StickyNote, ChevronDown, ChevronUp } from 'lucide-react'
import { liveConversation, type LiveStatus } from '../../lib/liveConversation'
import { desktopApi } from '../../lib/apiClient'
import { cn } from '../../lib/utils'

type Note = { id: string; text: string; auto: boolean; ts: number }

const WORD_THRESHOLD = 50

let wordCount = 0
let lastGenTs = 0

/**
 * Floating Live Notes panel — mirrors macOS LiveNotesView.
 * Appears while recording is active. Shows AI-generated notes from the live
 * transcript plus a manual input field. Collapses to a pill.
 */
export function LiveNotesPanel(): React.JSX.Element | null {
  const [status, setStatus] = useState<LiveStatus>(() => liveConversation.getStatus())
  const [notes, setNotes] = useState<Note[]>([])
  const [aiEnabled, setAiEnabled] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [manualText, setManualText] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const processedSegCountRef = useRef(0)
  const notesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    return liveConversation.subscribe(() => {
      setStatus(liveConversation.getStatus())
    })
  }, [])

  // Reset on each new session
  const isActive = status === 'live' || status === 'connecting'
  useEffect(() => {
    if (isActive) {
      setDismissed(false)
      wordCount = 0
      lastGenTs = 0
      processedSegCountRef.current = 0
    } else {
      // Reset word buffer when session ends
      wordCount = 0
    }
  }, [isActive])

  // Watch for new transcript words — generate a note every WORD_THRESHOLD words
  useEffect(() => {
    if (!isActive || !aiEnabled) return
    return liveConversation.subscribe(() => {
      if (!aiEnabled) return
      const segs = liveConversation.getSegments()
      const newSegs = segs.slice(processedSegCountRef.current)
      if (newSegs.length === 0) return
      processedSegCountRef.current = segs.length

      for (const seg of newSegs) {
        wordCount += seg.text.trim().split(/\s+/).filter(Boolean).length
      }

      const now = Date.now()
      if (wordCount >= WORD_THRESHOLD && now - lastGenTs > 5000) {
        wordCount = 0
        lastGenTs = now
        const transcript = segs
          .slice(Math.max(0, segs.length - 20))
          .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
          .join('\n')
        void generateNote(transcript)
      }
    })
  }, [isActive, aiEnabled])

  const generateNote = async (transcript: string): Promise<void> => {
    if (generating) return
    setGenerating(true)
    try {
      const res = await desktopApi.post('/v2/chat/completions', {
        model: 'gpt-4o-mini',
        messages: [
          {
            role: 'system',
            content:
              'Generate a single concise note (one short sentence) about the key point in this transcript segment. Be factual. No quotes. No prefixes like "Discussion about". Jump straight to the note.'
          },
          { role: 'user', content: transcript }
        ],
        max_tokens: 60,
        temperature: 0.3
      })
      const text = (res.data as { choices?: { message?: { content?: string } }[] })
        ?.choices?.[0]?.message?.content?.trim()
      if (text) {
        setNotes((n) => [...n, { id: crypto.randomUUID(), text, auto: true, ts: Date.now() }])
        setTimeout(() => notesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
      }
    } catch {
      // Silent — don't disrupt recording on AI failure
    } finally {
      setGenerating(false)
    }
  }

  const addManual = (): void => {
    const text = manualText.trim()
    if (!text) return
    setNotes((n) => [...n, { id: crypto.randomUUID(), text, auto: false, ts: Date.now() }])
    setManualText('')
    setTimeout(() => notesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
  }

  const deleteNote = (id: string): void => setNotes((n) => n.filter((x) => x.id !== id))

  if (!isActive || dismissed) return null

  return (
    <div className="pointer-events-none fixed bottom-4 left-4 z-40 w-64 max-w-[calc(100vw-2rem)]">
      <div className="pointer-events-auto glass-strong overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <StickyNote className="h-3 w-3 shrink-0 text-white/50" strokeWidth={1.75} />
          <span className="flex-1 text-xs font-semibold text-white/80">Live Notes</span>
          {/* AI toggle */}
          <button
            onClick={() => setAiEnabled((v) => !v)}
            title={aiEnabled ? 'Disable AI notes' : 'Enable AI notes'}
            className={cn(
              'flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] transition-colors',
              aiEnabled ? 'bg-[color:var(--accent)]/20 text-[color:var(--accent)]' : 'text-white/30 hover:text-white/60'
            )}
          >
            <Sparkles className="h-2.5 w-2.5" />
            AI
          </button>
          {generating && <Loader2 className="h-3 w-3 animate-spin text-white/30" />}
          <button onClick={() => setCollapsed((c) => !c)} className="rounded-md p-1 text-white/30 hover:bg-white/10 hover:text-white/70">
            {collapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          <button onClick={() => setDismissed(true)} className="rounded-md p-1 text-white/30 hover:bg-white/10 hover:text-white/70">
            <X className="h-3 w-3" />
          </button>
        </div>

        {!collapsed && (
          <>
            {/* Notes list */}
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto px-2 py-2">
              {notes.length === 0 ? (
                <p className="py-3 text-center text-[11px] text-white/30">
                  {aiEnabled ? 'Notes will appear as you speak…' : 'Add a note below'}
                </p>
              ) : (
                notes.map((note) => (
                  <div key={note.id} className="group flex items-start gap-2 rounded-lg bg-white/[0.04] px-2.5 py-2">
                    {note.auto && (
                      <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-[color:var(--accent)]/60" />
                    )}
                    <p className="flex-1 text-[11px] leading-relaxed text-white/80">{note.text}</p>
                    <button
                      onClick={() => deleteNote(note.id)}
                      className="mt-0.5 shrink-0 rounded p-0.5 text-white/20 opacity-0 transition-opacity hover:text-rose-400 group-hover:opacity-100"
                    >
                      <Trash2 className="h-2.5 w-2.5" />
                    </button>
                  </div>
                ))
              )}
              <div ref={notesEndRef} />
            </div>

            {/* Manual input */}
            <div className="border-t border-white/[0.06] px-2 py-2">
              <div className="flex items-center gap-1.5 rounded-lg bg-white/[0.06] px-2 py-1.5">
                <input
                  value={manualText}
                  onChange={(e) => setManualText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') addManual() }}
                  placeholder="Add a note…"
                  className="flex-1 bg-transparent text-[11px] text-white/80 placeholder:text-white/30 focus:outline-none"
                />
                <button
                  onClick={addManual}
                  disabled={!manualText.trim()}
                  className="rounded p-0.5 text-white/40 transition-colors hover:text-white/80 disabled:opacity-30"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
