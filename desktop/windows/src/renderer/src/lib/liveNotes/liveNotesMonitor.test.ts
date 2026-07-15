import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiveNote, TranscriptLine } from '../../../../shared/types'
import type { LiveStatus } from '../liveConversation'
import {
  LiveNotesMonitor,
  type LiveNoteGenerator,
  type LiveNoteStorage,
  type LiveTranscriptSource
} from './liveNotesMonitor'

// trackEvent is imported directly by the monitor (not injected), so mock it to
// assert the fallback telemetry on generation failure.
vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))
import { trackEvent } from '../analytics'

// A transcript line with `n` words under a stable id.
function line(id: string, n: number): TranscriptLine {
  return { id, text: Array.from({ length: n }, (_, i) => `w${i}`).join(' ') }
}

// Controllable fake of the live transcript store.
function makeFakeLive(): LiveTranscriptSource & {
  push(segments: TranscriptLine[], saved?: boolean): void
} {
  let segments: TranscriptLine[] = []
  let saved = false
  const status: LiveStatus = 'live'
  const subs = new Set<() => void>()
  return {
    getSegments: () => segments,
    getStatus: () => status,
    isSaved: () => saved,
    subscribe: (cb) => {
      subs.add(cb)
      return () => subs.delete(cb)
    },
    push(next, isSaved = false) {
      segments = next
      saved = isSaved
      subs.forEach((cb) => cb())
    }
  }
}

function makeFakeStorage(): LiveNoteStorage & { rows: LiveNote[] } {
  const rows: LiveNote[] = []
  return {
    rows,
    createSession: vi.fn(async () => {}),
    createNote: vi.fn(async (n: LiveNote) => {
      rows.push(n)
    }),
    updateNote: vi.fn(async () => {}),
    deleteNote: vi.fn(async () => {}),
    listNotes: vi.fn(async () => [])
  }
}

beforeEach(() => {
  vi.mocked(trackEvent).mockClear()
})

describe('LiveNotesMonitor', () => {
  it('generates an AI note after the word threshold and persists it', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const generator: LiveNoteGenerator = vi.fn(async () => '  "meeting agenda set" ')
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()

    live.push([line('a', 60)]) // > 50 words → one generation

    await vi.waitFor(() => expect(monitor.getNotes()).toHaveLength(1))
    const [note] = monitor.getNotes()
    expect(note.isAi).toBe(true)
    // Quotes stripped, whitespace trimmed (Mac's cleanup).
    expect(note.text).toBe('meeting agenda set')
    expect(storage.createNote).toHaveBeenCalledTimes(1)
    expect(storage.createSession).toHaveBeenCalledTimes(1)
    expect(monitor.isGenerating()).toBe(false)
  })

  it('is single-flight — no second generation while one is in flight', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    let resolve!: (v: string) => void
    const generator: LiveNoteGenerator = vi.fn(() => new Promise<string>((r) => (resolve = r)))
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()

    live.push([line('a', 60)])
    await vi.waitFor(() => expect(monitor.isGenerating()).toBe(true))
    // More words arrive mid-flight — must NOT start a second generation.
    live.push([line('a', 60), line('b', 60)])
    expect(generator).toHaveBeenCalledTimes(1)

    resolve('note')
    await vi.waitFor(() => expect(monitor.isGenerating()).toBe(false))
    expect(monitor.getNotes()).toHaveLength(1)
  })

  it('degrades gracefully when generation fails (transcript keeps working)', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const generator: LiveNoteGenerator = vi.fn(async () => {
      throw new Error('proxy 500')
    })
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()

    live.push([line('a', 60)])

    // A fallback event is recorded and the monitor recovers cleanly.
    await vi.waitFor(() => expect(trackEvent).toHaveBeenCalled())
    expect(trackEvent).toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({
        component: 'live_notes',
        reason: 'generation_failed',
        outcome: 'degraded'
      })
    )
    // No note was created, no crash, generating cleared, transcript untouched.
    expect(monitor.getNotes()).toHaveLength(0)
    expect(storage.createNote).not.toHaveBeenCalled()
    expect(monitor.isGenerating()).toBe(false)
    expect(live.getSegments()).toHaveLength(1)
  })

  it('stores a user-typed note as a separate row without overwriting AI notes', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const generator: LiveNoteGenerator = vi.fn(async () => 'ai bullet')
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()

    live.push([line('a', 60)])
    await vi.waitFor(() => expect(monitor.getNotes()).toHaveLength(1))

    await monitor.addManualNote('  remember to follow up  ')
    const notes = monitor.getNotes()
    expect(notes).toHaveLength(2)
    const manual = notes.find((n) => !n.isAi)
    expect(manual?.text).toBe('remember to follow up')
    // The AI note is still present and unchanged.
    expect(notes.filter((n) => n.isAi)).toHaveLength(1)
    expect(storage.rows).toHaveLength(2)
  })

  it('does not generate when AI is toggled off', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const generator: LiveNoteGenerator = vi.fn(async () => 'x')
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()
    monitor.setAiEnabled(false)

    live.push([line('a', 120)])
    await new Promise((r) => setTimeout(r, 10))
    expect(generator).not.toHaveBeenCalled()
    expect(monitor.getNotes()).toHaveLength(0)
  })

  it('keeps notes on finalize but clears them when a new conversation starts', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const generator: LiveNoteGenerator = vi.fn(async () => 'note')
    const monitor = new LiveNotesMonitor(generator, storage, live)
    monitor.start()

    live.push([line('a', 60)])
    await vi.waitFor(() => expect(monitor.getNotes()).toHaveLength(1))

    // Finalized: transcript flagged saved — notes stay visible.
    live.push([line('a', 60)], true)
    expect(monitor.getNotes()).toHaveLength(1)

    // Next conversation's first words arrive (saved cleared) — notes reset.
    live.push([line('b', 3)])
    expect(monitor.getNotes()).toHaveLength(0)
  })

  it('edits and deletes notes', async () => {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const monitor = new LiveNotesMonitor(
      vi.fn(async () => ''),
      storage,
      live
    )
    monitor.start()
    live.push([line('a', 3)]) // starts a session (below threshold, no AI note)

    await monitor.addManualNote('first')
    const id = monitor.getNotes()[0].id
    await monitor.updateNote(id, 'edited')
    expect(monitor.getNotes()[0].text).toBe('edited')
    expect(storage.updateNote).toHaveBeenCalledWith(id, 'edited', expect.any(Number))

    await monitor.deleteNote(id)
    expect(monitor.getNotes()).toHaveLength(0)
    expect(storage.deleteNote).toHaveBeenCalledWith(id)
  })

  // Drive `updates` post-threshold word-updates, each +60 fresh words, letting the
  // single-flight generation settle between them. Returns the monitor + generator.
  async function driveFailingSession(
    generator: LiveNoteGenerator,
    updates: number,
    clock?: () => number
  ): Promise<{ monitor: LiveNotesMonitor; live: ReturnType<typeof makeFakeLive> }> {
    const live = makeFakeLive()
    const storage = makeFakeStorage()
    const monitor = new LiveNotesMonitor(generator, storage, live, clock)
    monitor.start()
    for (let i = 0; i < updates; i++) {
      live.push([line('a', 60 + i * 60)]) // +60 new words each update → a request
      await vi.waitFor(() => expect(monitor.isGenerating()).toBe(false))
    }
    return { monitor, live }
  }

  it('cost guard: stops re-firing after N consecutive failures (bounded proxy calls)', async () => {
    // A persistently broken proxy. Without the breaker this would re-fire on every
    // one of the 12 word-updates; with it, calls are capped at MAX (3).
    const generator: LiveNoteGenerator = vi.fn(async () => {
      throw new Error('proxy 500 (non-retryable)')
    })
    await driveFailingSession(generator, 12)
    expect(generator).toHaveBeenCalledTimes(3)
  })

  it('cost guard: a new session resets the breaker and generation resumes', async () => {
    let fail = true
    const generator: LiveNoteGenerator = vi.fn(async () => {
      if (fail) throw new Error('down')
      return 'recovered note'
    })
    const { monitor, live } = await driveFailingSession(generator, 6)
    expect(generator).toHaveBeenCalledTimes(3) // circuit open

    // Finalize, then a new conversation's words — startSession resets the circuit.
    fail = false
    live.push([line('a', 360)], true) // saved (finalized)
    live.push([line('b', 60)]) // new session, fresh words
    await vi.waitFor(() => expect(monitor.getNotes()).toHaveLength(1))
    expect(generator).toHaveBeenCalledTimes(4) // one probe after the reset, succeeded
  })

  it('cost guard: probes again once the cool-off elapses (half-open)', async () => {
    let t = 1_000_000
    let fail = true
    const generator: LiveNoteGenerator = vi.fn(async () => {
      if (fail) throw new Error('down')
      return 'note after cooloff'
    })
    const { monitor, live } = await driveFailingSession(generator, 6, () => t)
    expect(generator).toHaveBeenCalledTimes(3) // open; still-in-cooloff updates suppressed

    // Advance past the cool-off and recover the proxy — the next update probes once.
    t += 61_000
    fail = false
    live.push([line('a', 500)])
    await vi.waitFor(() => expect(monitor.getNotes()).toHaveLength(1))
    expect(generator).toHaveBeenCalledTimes(4)
  })
})
