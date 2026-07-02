import { create } from 'zustand'
import { api } from '../api/client'
import type { Person, ServerConversation, ServerTranscriptSegment } from '../api/types'
import type { TranscriptSegment } from '../../../shared/types'
import { PcmCapture } from '../lib/audio'
import { chatCompletion } from '../api/chat'
import { assignSpeakerToSegments, loadPeople as fetchPeople } from '../lib/speakers'

interface ConversationsStore {
  items: ServerConversation[]
  loading: boolean
  selectedId: string | null
  selected: ServerConversation | null
  searchQuery: string
  error: string | null
  people: Person[]
  load: () => Promise<void>
  loadPeople: () => Promise<void>
  select: (id: string | null) => Promise<void>
  search: (q: string) => Promise<void>
  toggleStar: (id: string) => Promise<void>
  remove: (id: string) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  /**
   * Tag a set of segments (by their segment objects) of the selected conversation
   * with a speaker, either the user or a person id, and optimistically reflect
   * it in the loaded transcript. Mirrors the Mac NameSpeakerSheet save path.
   */
  assignSpeaker: (
    conversationId: string,
    segments: ServerTranscriptSegment[],
    target: { isUser: boolean; personId?: string | null }
  ) => Promise<boolean>
}

export const useConversations = create<ConversationsStore>((set, get) => ({
  items: [],
  loading: false,
  selectedId: null,
  selected: null,
  searchQuery: '',
  error: null,
  people: [],
  loadPeople: async () => {
    const people = await fetchPeople()
    set({ people })
  },
  load: async () => {
    set({ loading: true, error: null })
    try {
      const items = await api.listConversations(50, 0)
      set({ items, loading: false })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },
  select: async (id) => {
    set({ selectedId: id, selected: id ? (get().items.find((c) => c.id === id) ?? null) : null })
    if (!id) return
    try {
      const full = await api.getConversation(id)
      if (get().selectedId === id) set({ selected: full })
    } catch {
      // keep the list version
    }
  },
  search: async (q) => {
    set({ searchQuery: q })
    if (!q.trim()) {
      await get().load()
      return
    }
    set({ loading: true })
    try {
      const res = await api.searchConversations(q)
      set({ items: res.items, loading: false })
    } catch (e) {
      set({ loading: false, error: String(e) })
    }
  },
  toggleStar: async (id) => {
    const conv = get().items.find((c) => c.id === id)
    if (!conv) return
    const starred = !conv.starred
    set({ items: get().items.map((c) => (c.id === id ? { ...c, starred } : c)) })
    try {
      await api.setConversationStarred(id, starred)
    } catch {
      set({ items: get().items.map((c) => (c.id === id ? { ...c, starred: !starred } : c)) })
    }
  },
  remove: async (id) => {
    set({
      items: get().items.filter((c) => c.id !== id),
      selectedId: get().selectedId === id ? null : get().selectedId,
      selected: get().selectedId === id ? null : get().selected
    })
    try {
      await api.deleteConversation(id)
    } catch {
      await get().load()
    }
  },
  rename: async (id, title) => {
    set({
      items: get().items.map((c) => (c.id === id ? { ...c, structured: { ...c.structured, title } } : c)),
      selected:
        get().selected?.id === id
          ? { ...get().selected!, structured: { ...get().selected!.structured, title } }
          : get().selected
    })
    await api.setConversationTitle(id, title)
  },
  assignSpeaker: async (conversationId, segments, target) => {
    const ok = await assignSpeakerToSegments(conversationId, segments, target)
    if (!ok) return false
    // Optimistically tag the matching segments in the loaded conversation.
    const ids = new Set(segments.map((s) => s.id).filter(Boolean) as string[])
    const apply = (seg: ServerTranscriptSegment): ServerTranscriptSegment =>
      seg.id && ids.has(seg.id)
        ? {
            ...seg,
            is_user: target.isUser,
            person_id: target.isUser ? null : (target.personId ?? null)
          }
        : seg
    const sel = get().selected
    if (sel?.id === conversationId && sel.transcript_segments) {
      set({ selected: { ...sel, transcript_segments: sel.transcript_segments.map(apply) } })
    }
    set({
      items: get().items.map((c) =>
        c.id === conversationId && c.transcript_segments
          ? { ...c, transcript_segments: c.transcript_segments.map(apply) }
          : c
      )
    })
    return true
  }
}))

// ---- Live recording (the Mac app's AudioSourceManager + TranscriptionService loop) ----

export type RecordingStatus = 'idle' | 'connecting' | 'recording' | 'stopping'

interface LiveStore {
  status: RecordingStatus
  segments: TranscriptSegment[]
  notes: string[]
  level: number
  systemAudio: boolean
  statusDetail: string | null
  /** Epoch ms when the current recording started (null when idle). */
  startedAt: number | null
  /** Whole seconds elapsed since the recording started, ticked every second. */
  elapsedSeconds: number
  setSystemAudio: (v: boolean) => void
  start: () => Promise<void>
  stop: () => Promise<void>
}

let capture: PcmCapture | null = null
let unsubEvents: (() => void) | null = null
let elapsedTimer: number | null = null

function clearElapsedTimer(): void {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

// Live notes: generate a short note every ~50 new transcript words (LiveNotesMonitor.swift).
let liveNotesCursor = 0
let liveNotesBusy = false
// Bumped on every start()/stop() so a note generation that resolves after the user
// switched recordings is discarded instead of leaking into the new session.
let liveNotesGen = 0
async function maybeGenerateNote(): Promise<void> {
  if (liveNotesBusy) return
  const segs = useLive.getState().segments
  const fullText = segs.map((s) => s.text).join(' ')
  const words = fullText.split(/\s+/).filter(Boolean)
  if (words.length - liveNotesCursor < 50) return
  liveNotesBusy = true
  const gen = liveNotesGen
  const excerpt = words.slice(Math.max(0, words.length - 120)).join(' ')
  liveNotesCursor = words.length
  try {
    const existing = useLive.getState().notes.slice(-10).join('; ')
    const note = await chatCompletion(
      [
        {
          role: 'system',
          content:
            'You are a concise meeting note-taker. Given a transcript excerpt, output ONE note of 3-10 words capturing the key point. No quotes, no preamble, be specific, avoid repeating existing notes.'
        },
        { role: 'user', content: `Existing notes: ${existing || 'none'}\n\nTranscript:\n${excerpt}` }
      ],
      'claude-haiku-4-5-20251001'
    )
    const clean = note.trim().replace(/^["'-\s]+|["'\s]+$/g, '')
    // Only attach the note if the recording that triggered it is still active.
    if (clean && gen === liveNotesGen) useLive.setState({ notes: [...useLive.getState().notes, clean] })
  } catch {
    // best-effort
  } finally {
    liveNotesBusy = false
  }
}

export const useLive = create<LiveStore>((set, get) => ({
  status: 'idle',
  segments: [],
  notes: [],
  level: 0,
  systemAudio: true,
  statusDetail: null,
  startedAt: null,
  elapsedSeconds: 0,
  setSystemAudio: (v) => set({ systemAudio: v }),
  start: async () => {
    if (get().status !== 'idle') return
    const startedAt = Date.now()
    set({ status: 'connecting', segments: [], notes: [], statusDetail: null, startedAt, elapsedSeconds: 0 })
    liveNotesCursor = 0
    liveNotesGen++
    liveNotesBusy = false

    // Tick the live elapsed counter once a second off the wall clock.
    if (elapsedTimer) clearInterval(elapsedTimer)
    elapsedTimer = window.setInterval(() => {
      const s = get().startedAt
      if (s === null) return
      set({ elapsedSeconds: Math.floor((Date.now() - s) / 1000) })
    }, 1000)

    unsubEvents?.()
    unsubEvents = window.omi.transcribe.onEvent('conversation', (event) => {
      if (event.type === 'segments') {
        const merged = [...get().segments]
        const indexById = new Map(merged.map((s, i) => [s.id, i]).filter(([id]) => id !== undefined) as [string, number][])
        for (const seg of event.segments) {
          const idx = seg.id !== undefined ? indexById.get(seg.id) : undefined
          if (idx !== undefined) {
            merged[idx] = seg
          } else {
            if (seg.id !== undefined) indexById.set(seg.id, merged.length)
            merged.push(seg)
          }
        }
        set({ segments: merged })
        void maybeGenerateNote()
      } else if (event.type === 'status') {
        if (event.status === 'connected') set({ status: 'recording' })
        else if (event.status === 'error') set({ statusDetail: event.detail ?? 'connection error' })
        else if (event.status === 'closed' && get().status === 'recording') {
          set({ statusDetail: 'connection closed' })
        }
      }
    })

    const ok = await window.omi.transcribe.start('conversation')
    if (!ok) {
      clearElapsedTimer()
      set({ status: 'idle', statusDetail: 'Sign in to start recording', startedAt: null, elapsedSeconds: 0 })
      return
    }

    capture = new PcmCapture()
    try {
      await capture.start({
        systemAudio: get().systemAudio,
        onFrame: (frame) => window.omi.transcribe.sendAudio('conversation', frame),
        onLevel: (rms) => set({ level: rms })
      })
    } catch (e) {
      window.omi.transcribe.stop('conversation')
      clearElapsedTimer()
      set({ status: 'idle', statusDetail: `Microphone unavailable: ${e}`, startedAt: null, elapsedSeconds: 0 })
      return
    }
  },
  stop: async () => {
    if (get().status === 'idle') return
    // Invalidate any in-flight live-note generation from this recording.
    liveNotesGen++
    liveNotesBusy = false
    clearElapsedTimer()
    set({ status: 'stopping' })
    capture?.stop()
    capture = null
    window.omi.transcribe.stop('conversation')
    unsubEvents?.()
    unsubEvents = null
    try {
      await api.forceProcessConversation()
    } catch {
      // backend will time the conversation out on its own
    }
    set({ status: 'idle', level: 0, startedAt: null, elapsedSeconds: 0 })
    await useConversations.getState().load()
  }
}))
