// PR8 LiveNotes — the monitor: subscribes to the live transcript store and drives
// AI note generation, plus user-typed note add/edit/delete. A faithful port of the
// macOS LiveNotesMonitor (Desktop/Sources/LiveNotes/LiveNotesMonitor.swift), a
// subscribable singleton so the notes panel can `subscribe()` exactly like it
// reads `liveConversation` — reusing the ALREADY-mirrored transcript stream (fed
// by LiveMirrorHost ← IPC ← the capture window). No new WebSocket/IPC for reads.
//
// Where it runs: mounted once at the app-shell root (LiveNotesHost), so generation
// runs whenever the main window is open regardless of whether the notes PANEL is
// open — matching Mac's "generation is tied to the transcription lifecycle, not
// the panel". (It is main-window-scoped, like the transcript mirror it reads;
// headless continuous recording with the window closed pauses generation, same as
// the mirror. Documented divergence — see the report.)
//
// Session model: the capture window owns the real client_conversation_id, which is
// NOT carried in the mirrored store, so the monitor mints its OWN session id when a
// new transcript starts and persists a transcription_sessions row (the anchor for
// the notes' cascading FK). Nothing joins sessions to conversations, so a
// monitor-minted id is self-consistent.

import type { LiveNote, TranscriptLine } from '../../../../shared/types'
import { liveConversation, type LiveStatus } from '../liveConversation'
import { generate as geminiGenerate } from '../geminiClient'
import { trackEvent } from '../analytics'
import { LiveNotesAccumulator, type LiveNotesGenerationRequest } from './liveNotesAccumulator'

// Mac's prompts, verbatim (LiveNotesMonitor.swift:64-72, 262).
const NOTE_GENERATION_PROMPT = `generate a single, concise note about what happened in this segment.
be factual and specific.
focus on the key point or action item.
keep it a few word sentence.
do not use quotes.
do not use wrapping words like "discussion on", jump straight into note.
avoid repeating information from existing notes.`

const SYSTEM_PROMPT =
  'You are a concise note-taker. Generate a single short note (3-10 words) about the key point in the transcript. Do not use quotes. Be direct and specific.'

// Gemini Flash on the premium tier (Mac's ModelQoS.Gemini.proactive default);
// thinkingBudget 0 = thinking disabled (cheapest), matching Mac's LiveNotes which
// passes no custom budget. Max-tier pro upgrade is deferred (documented).
const NOTE_MODEL = 'gemini-2.5-flash'

/** Turns a transcript segment + existing notes into a note string. Injected so
 *  tests never hit the network. */
export type LiveNoteGenerator = (prompt: string, systemPrompt: string) => Promise<string>

/** Local-only persistence for notes + their session anchor. Injected so tests
 *  never touch Electron IPC / SQLite. */
export interface LiveNoteStorage {
  createSession(session: { id: string; startedAt: number; createdAt: number }): Promise<void>
  createNote(note: LiveNote): Promise<void>
  updateNote(id: string, text: string, updatedAt: number): Promise<void>
  deleteNote(id: string): Promise<void>
  listNotes(sessionId: string): Promise<LiveNote[]>
}

/** Minimal read/subscribe surface of the live transcript store (injectable). */
export interface LiveTranscriptSource {
  getSegments(): TranscriptLine[]
  getStatus(): LiveStatus
  isSaved(): boolean
  subscribe(cb: () => void): () => void
}

const defaultGenerator: LiveNoteGenerator = (prompt, systemPrompt) =>
  geminiGenerate({
    model: NOTE_MODEL,
    parts: [{ text: prompt }],
    systemPrompt,
    thinkingBudget: 0
  })

const defaultStorage: LiveNoteStorage = {
  createSession: (s) => window.omi.createTranscriptionSession(s),
  createNote: (n) => window.omi.createLiveNote(n),
  updateNote: (id, text, updatedAt) => window.omi.updateLiveNote(id, text, updatedAt),
  deleteNote: (id) => window.omi.deleteLiveNote(id),
  listNotes: (sessionId) => window.omi.listLiveNotes(sessionId)
}

function newId(): string {
  return crypto.randomUUID()
}

// Map the transcript store's lines to accumulator segments, giving id-less lines a
// stable positional key (the store only appends/upserts, never reorders, so index
// is stable for a given line).
function toAccumulatorSegments(segments: TranscriptLine[]): { id: string; text: string }[] {
  return segments.map((s, i) => ({ id: s.id ?? `#${i}`, text: s.text }))
}

export class LiveNotesMonitor {
  private notes: LiveNote[] = []
  private generating = false
  private aiEnabled = true
  private currentSessionId: string | null = null
  private accumulator = new LiveNotesAccumulator()
  private readonly subscribers = new Set<() => void>()
  private unsubscribeTranscript: (() => void) | null = null
  private startCount = 0

  constructor(
    private readonly generator: LiveNoteGenerator = defaultGenerator,
    private readonly storage: LiveNoteStorage = defaultStorage,
    private readonly live: LiveTranscriptSource = liveConversation
  ) {}

  // --- Public read surface (the panel subscribes like it does to liveConversation) ---

  getNotes(): LiveNote[] {
    return this.notes
  }
  isGenerating(): boolean {
    return this.generating
  }
  isAiEnabled(): boolean {
    return this.aiEnabled
  }
  subscribe(cb: () => void): () => void {
    this.subscribers.add(cb)
    return () => {
      this.subscribers.delete(cb)
    }
  }

  private notify(): void {
    this.subscribers.forEach((cb) => cb())
  }

  // --- Lifecycle (mounted once by LiveNotesHost; refcounted for StrictMode) ---

  /** Begin observing the transcript. Refcounted so a StrictMode double-mount
   *  subscribes exactly once (a second subscription would double-generate). */
  start(): () => void {
    this.startCount++
    if (this.startCount === 1) {
      this.unsubscribeTranscript = this.live.subscribe(() => this.onTranscriptChange())
      // Apply the current state immediately (a session may already be live).
      this.onTranscriptChange()
    }
    return () => this.stop()
  }

  private stop(): void {
    this.startCount = Math.max(0, this.startCount - 1)
    if (this.startCount === 0) {
      this.unsubscribeTranscript?.()
      this.unsubscribeTranscript = null
    }
  }

  private onTranscriptChange(): void {
    const segments = this.live.getSegments()
    const saved = this.live.isSaved()

    // End: the conversation finalized (saved — keep its notes visible) or the
    // session was torn down (segments cleared — clear the list too).
    if (this.currentSessionId !== null && (saved || segments.length === 0)) {
      this.endSession(segments.length === 0 && !saved)
    }

    // Start: a new transcript is flowing with no active session.
    if (this.currentSessionId === null && segments.length > 0 && !saved) {
      this.startSession()
    }

    if (this.currentSessionId === null || !this.aiEnabled) return

    const request = this.accumulator.handleSegmentsUpdate(
      toAccumulatorSegments(segments),
      this.generating
    )
    if (request) void this.generateNote(request)
  }

  private startSession(): void {
    const id = newId()
    const now = Date.now()
    this.currentSessionId = id
    this.notes = []
    this.generating = false
    this.accumulator.reset()
    // Persist the anchor (best-effort — a failed insert must not stop generation;
    // FKs are off so a note with a missing session row still inserts).
    void this.storage.createSession({ id, startedAt: now, createdAt: now }).catch((e) => {
      console.warn('[live-notes] createSession failed:', (e as Error).message)
    })
    this.notify()
  }

  /** End the current session. Keep the notes visible when finalized (saved); clear
   *  them on a hard teardown so the next session starts blank. */
  private endSession(clearNotes: boolean): void {
    this.currentSessionId = null
    this.generating = false
    this.accumulator.reset()
    if (clearNotes && this.notes.length) {
      this.notes = []
      this.notify()
    }
  }

  // --- Manual notes (from the panel) ---

  /** Add a user-typed note. Mints a session if none is active yet (a note typed
   *  while connecting must not be lost — a safe improvement over Mac, which drops
   *  it). Feeds the accumulator context so the AI won't repeat it. */
  async addManualNote(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed) return
    const sessionId = this.ensureSession()
    const now = Date.now()
    const note: LiveNote = {
      id: newId(),
      sessionId,
      text: trimmed,
      isAi: false,
      segStart: this.accumulator.segmentOrder,
      segEnd: null,
      createdAt: now,
      updatedAt: now
    }
    try {
      await this.storage.createNote(note)
    } catch (e) {
      console.warn('[live-notes] add manual note failed:', (e as Error).message)
      return
    }
    if (this.currentSessionId !== sessionId) return // session changed mid-await
    this.notes = [...this.notes, note]
    this.accumulator.appendExistingNote(trimmed)
    this.notify()
  }

  /** Edit a note's text (explicit user action). Reseeds accumulator context. */
  async updateNote(id: string, text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed) return
    const now = Date.now()
    try {
      await this.storage.updateNote(id, trimmed, now)
    } catch (e) {
      console.warn('[live-notes] update note failed:', (e as Error).message)
      return
    }
    this.notes = this.notes.map((n) => (n.id === id ? { ...n, text: trimmed, updatedAt: now } : n))
    this.accumulator.seedExistingNotes(this.notes.map((n) => n.text))
    this.notify()
  }

  /** Delete a note (explicit user action). Reseeds accumulator context. */
  async deleteNote(id: string): Promise<void> {
    try {
      await this.storage.deleteNote(id)
    } catch (e) {
      console.warn('[live-notes] delete note failed:', (e as Error).message)
      return
    }
    this.notes = this.notes.filter((n) => n.id !== id)
    this.accumulator.seedExistingNotes(this.notes.map((n) => n.text))
    this.notify()
  }

  setAiEnabled(enabled: boolean): void {
    if (this.aiEnabled === enabled) return
    this.aiEnabled = enabled
    this.notify()
  }

  private ensureSession(): string {
    if (this.currentSessionId) return this.currentSessionId
    this.startSession()
    return this.currentSessionId as unknown as string
  }

  // --- AI generation (single-flight; the accumulator already gated the trigger) ---

  private async generateNote(request: LiveNotesGenerationRequest): Promise<void> {
    const sessionId = this.currentSessionId
    if (sessionId === null || !this.aiEnabled || this.generating) return
    this.generating = true
    this.notify()

    const prompt = `Transcript segment:\n${request.recentText}\n\n${request.existingNotesText}\n\n${NOTE_GENERATION_PROMPT}`

    try {
      const raw = await this.generator(prompt, SYSTEM_PROMPT)
      // Clean up (Mac: trim, strip straight quotes/apostrophes).
      const noteText = raw.trim().replace(/["']/g, '')
      if (!noteText) {
        this.finishGeneration(sessionId)
        return
      }
      if (this.currentSessionId !== sessionId) {
        this.finishGeneration(sessionId)
        return
      }
      const now = Date.now()
      const note: LiveNote = {
        id: newId(),
        sessionId,
        text: noteText,
        isAi: true,
        segStart: request.segmentStartOrder,
        segEnd: request.segmentEndOrder,
        createdAt: now,
        updatedAt: now
      }
      await this.storage.createNote(note)
      if (this.currentSessionId !== sessionId) {
        this.finishGeneration(sessionId)
        return
      }
      this.notes = [...this.notes, note]
      this.accumulator.markGenerationSucceeded(noteText)
      this.finishGeneration(sessionId)
    } catch (e) {
      // Generation (or its persist) failed. Degrade gracefully: the transcript is
      // untouched and keeps working, we simply skip this note and the accumulator
      // will retry on the next threshold. This is a provider/fail-open branch, so
      // record it as a fallback (AGENTS.md → Fallback / resilience telemetry). The
      // Windows app has no recordFallback wrapper; the established idiom is a
      // trackEvent('fallback_triggered', …) with the same fields.
      trackEvent('fallback_triggered', {
        component: 'live_notes',
        from: 'gemini',
        to: 'none',
        reason: 'generation_failed',
        outcome: 'degraded'
      })
      console.warn('[live-notes] generation failed:', (e as Error).message)
      this.finishGeneration(sessionId)
    }
  }

  private finishGeneration(sessionId: string): void {
    // Only clear the flag if we still own this session (a teardown may have
    // reset it). Always notify so a spinner stops.
    if (this.currentSessionId === sessionId || this.currentSessionId === null) {
      this.generating = false
    }
    this.notify()
  }
}

// The app-wide singleton the host mounts and the panel subscribes to.
export const liveNotesMonitor = new LiveNotesMonitor()
