// Hermetic tests for the warm-hub PTT DRIVER (A5 PR-6b) — the cross-window ON-path.
// Every collaborator is a fake, so no window, WebSocket, mic, or pcmPlayer is
// touched. Covers the four brief-required cases and the core turn lifecycles.
import { describe, it, expect, vi } from 'vitest'
import {
  VoiceHubTurnDriver,
  RELEASE_WATCHDOG_HINT,
  concatInt16,
  pcm16ToBytes,
  bytesToPcm16,
  pcmPeakLevel,
  resamplePcm16,
  type VoiceHubTurnDriverDeps
} from './voiceHubTurnDriver'
import type { HubController, HubControllerEvents } from '../hub/hubController'
import type { PttCapture, PttCaptureOptions } from '../../ptt/capture'
import type { VoiceHubBarState } from '../../../../../shared/types'
import type {
  VoiceCaptureID,
  VoiceSessionID,
  VoiceTurnID,
  VoiceTurnDeadline
} from './voiceTurnMachine'
import type {
  VoiceTurnDeadlineCancellation,
  VoiceTurnDeadlineScheduling
} from './voiceTurnCoordinator'

// ---- fakes ----------------------------------------------------------------

/** A manual clock so the 1 s hubWarm deadline (and any other) fires on command. */
class ManualScheduler implements VoiceTurnDeadlineScheduling {
  private entries: { deadline: string; fire: () => void; cancelled: boolean }[] = []
  schedule(
    deadline: VoiceTurnDeadline,
    _after: number,
    fire: () => void
  ): VoiceTurnDeadlineCancellation {
    const entry = { deadline: deadline as string, fire, cancelled: false }
    this.entries.push(entry)
    return { cancel: () => (entry.cancelled = true) }
  }
  fire(deadline: string): void {
    for (const e of this.entries) if (e.deadline === deadline && !e.cancelled) e.fire()
  }
}

function makeFakeHub() {
  let warm = false
  let available = false
  let events: HubControllerEvents = {}
  const calls = {
    beginTurn: [] as { turnID: VoiceTurnID; interrupting: boolean }[],
    appendAudio: 0,
    commitTurn: [] as VoiceTurnID[],
    cancelTurn: [] as VoiceTurnID[],
    handoff: [] as VoiceTurnID[],
    didTerminate: [] as VoiceTurnID[],
    seedProduced: [] as string[],
    seedRefresh: 0,
    ensureWarm: 0,
    teardown: 0,
    sendToolResult: [] as { callId: string; name: string; output: string }[]
  }
  let warmError: unknown = null
  const hub = {
    isWarm: () => warm,
    isAvailable: () => available,
    requiredInputSampleRate: () => (warm || available ? 24000 : null),
    ensureWarm: () => {
      calls.ensureWarm++
      // A rejected warm (mint failure / teardown-during-warm abort) — the driver's
      // fire-and-forget warm() must swallow it (no unhandled rejection).
      if (warmError !== null) return Promise.reject(warmError)
      return Promise.resolve('sess' as VoiceSessionID)
    },
    beginTurn: (turnID: VoiceTurnID, opts: { interrupting?: boolean } = {}) =>
      calls.beginTurn.push({ turnID, interrupting: opts.interrupting ?? false }),
    appendAudio: () => {
      calls.appendAudio++
    },
    commitTurn: (turnID: VoiceTurnID) => calls.commitTurn.push(turnID),
    cancelTurn: (turnID: VoiceTurnID) => calls.cancelTurn.push(turnID),
    handoffWarmWaitToCascade: (turnID: VoiceTurnID) => calls.handoff.push(turnID),
    voiceTurnDidTerminate: (turnID: VoiceTurnID) => calls.didTerminate.push(turnID),
    teardownSession: () => {
      calls.teardown++
    },
    markSeedKeyProduced: (key: string) => calls.seedProduced.push(key),
    refreshSeedContext: () => {
      calls.seedRefresh++
    },
    sendToolResult: (callId: string, name: string, output: string) =>
      calls.sendToolResult.push({ callId, name, output })
  }
  return {
    factory: (e: HubControllerEvents): HubController => {
      events = e
      return hub as unknown as HubController
    },
    events: () => events,
    setAvailability: (w: boolean, a: boolean = w) => {
      warm = w
      available = a
    },
    failNextWarm: (e: unknown) => {
      warmError = e
    },
    calls
  }
}

function makeFakeCapture() {
  let onChunk: ((pcm: Int16Array) => void) | undefined
  let onLevels: ((orbLevel: number) => void) | undefined
  const cap: PttCapture = {
    analyser: { getByteFrequencyData: () => {}, getOrbLevel: () => 0 },
    drain: () => Promise.resolve(new Int16Array(0)),
    dispose: vi.fn()
  }
  const start = vi.fn((opts: PttCaptureOptions): Promise<PttCapture> => {
    onChunk = opts.onChunk
    onLevels = opts.onLevels
    return Promise.resolve(cap)
  })
  return {
    start,
    feed: (pcm: Int16Array) => onChunk?.(pcm),
    feedLevel: (orbLevel: number) => onLevels?.(orbLevel),
    cap
  }
}

type Harness = {
  driver: VoiceHubTurnDriver
  hub: ReturnType<typeof makeFakeHub>
  capture: ReturnType<typeof makeFakeCapture>
  scheduler: ManualScheduler
  states: VoiceHubBarState[]
  /** The release watchdog seam — `fire()` simulates RELEASE_WATCHDOG_MS elapsing. */
  watchdog: { armed: boolean; cancelled: boolean; fire: () => void }
  spies: {
    interruptPlayback: ReturnType<typeof vi.fn>
    transcribe: ReturnType<typeof vi.fn>
    onFinalText: ReturnType<typeof vi.fn>
    onRecordTurn: ReturnType<typeof vi.fn>
    muteForCapture: ReturnType<typeof vi.fn>
    restoreSystemAudio: ReturnType<typeof vi.fn>
    trackEvent: ReturnType<typeof vi.fn>
  }
}

function makeDriver(
  opts: {
    pttHubEnabled?: boolean
    transcript?: string
    executeTool?: (name: string, argumentsJSON: string) => Promise<string>
  } = {}
): Harness {
  const hub = makeFakeHub()
  const capture = makeFakeCapture()
  const scheduler = new ManualScheduler()
  const states: VoiceHubBarState[] = []
  let turnSeq = 0
  let clock = 0
  const spies = {
    interruptPlayback: vi.fn(),
    transcribe: vi.fn(() => Promise.resolve(opts.transcript ?? 'hello world')),
    onFinalText: vi.fn(),
    onRecordTurn: vi.fn(),
    muteForCapture: vi.fn(),
    restoreSystemAudio: vi.fn(),
    trackEvent: vi.fn()
  }
  const watchdog: Harness['watchdog'] = { armed: false, cancelled: false, fire: () => {} }
  const deps: VoiceHubTurnDriverDeps = {
    createHub: hub.factory,
    scheduleReleaseWatchdog: (fire) => {
      watchdog.armed = true
      watchdog.cancelled = false
      watchdog.fire = fire
      return {
        cancel: () => {
          watchdog.cancelled = true
        }
      }
    },
    interruptPlayback: spies.interruptPlayback,
    publishState: (s) => states.push(s),
    startCapture: capture.start,
    transcribe: spies.transcribe,
    onFinalText: spies.onFinalText,
    onRecordTurn: spies.onRecordTurn,
    muteForCapture: spies.muteForCapture,
    restoreSystemAudio: spies.restoreSystemAudio,
    trackEvent: spies.trackEvent,
    executeTool: opts.executeTool,
    prefs: () => ({ pttHubEnabled: opts.pttHubEnabled }),
    scheduler,
    mintTurnID: () => `turn-${++turnSeq}` as VoiceTurnID,
    mintCaptureID: () => ++turnSeq as unknown as VoiceCaptureID,
    now: () => (clock += 1000) // strictly increasing so the orb throttle never blocks
  }
  return { driver: new VoiceHubTurnDriver(deps), hub, capture, scheduler, states, watchdog, spies }
}

const flush = (): Promise<void> => Promise.resolve().then(() => {})
const loud = (): Int16Array => Int16Array.from([0, 16000, -16000, 8000])
/** 1s of fully-voiced 16kHz audio — passes the cascade release gate
 *  (total ≥ 0.35s, voiced ≥ 0.2s, peak above the dead-mic floor). */
const voiced1s = (): Int16Array => new Int16Array(16000).fill(8000)

// ---- (a) the invariant: flag OFF never engages the hub --------------------

describe('kill-switch (flag off)', () => {
  it('with the flag off, begin() never touches the hub — the route is the cascade', async () => {
    const h = makeDriver({ pttHubEnabled: false })
    h.hub.setAvailability(true) // even a warm hub must be bypassed when the flag is off
    h.driver.begin({ backfillMs: 0 })
    await flush()
    expect(h.hub.calls.beginTurn).toHaveLength(0)
    expect(h.hub.calls.appendAudio).toBe(0)
    expect(h.capture.start).toHaveBeenCalledTimes(1) // main-owned capture still issued
  })

  it('warm() is inert when the flag is off', () => {
    const h = makeDriver({ pttHubEnabled: false })
    h.driver.warm()
    expect(h.hub.calls.ensureWarm).toBe(0)
  })

  it('warm() swallows a rejected ensureWarm (no unhandled rejection)', async () => {
    // Eager warm is fire-and-forget; a mint failure (both providers down) or a
    // teardown-during-warm abort (HubWarmAbortedError) must not leak. If warm()
    // floated the rejection, vitest would fail this test with an unhandled rejection.
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.failNextWarm(new Error('mint failed / warm aborted'))
    h.driver.warm()
    await Promise.resolve()
    await Promise.resolve()
    expect(h.hub.calls.ensureWarm).toBe(1)
  })
})

// ---- (b) flag ON: begin starts a main-owned hub turn ----------------------

describe('begin (flag on, hub warm)', () => {
  it('starts a main-owned hub turn: capture issued here, hub.beginTurn, orb listening', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 40 })

    // Capture ownership is issued FROM THIS renderer (the production seam that makes
    // main the owner), with the backfill forwarded.
    expect(h.capture.start).toHaveBeenCalledTimes(1)
    expect(h.capture.start.mock.calls[0][0].backfillMs).toBe(40)
    // The hub turn began.
    expect(h.hub.calls.beginTurn).toHaveLength(1)
    // The orb is told a main-owned turn is listening.
    const last = h.states.at(-1)!
    expect(last.active).toBe(true)
    expect(last.isListening).toBe(true)

    await flush()
    // Once capture confirms, frames feed the hub.
    h.capture.feed(loud())
    expect(h.hub.calls.appendAudio).toBe(1)
  })

  it('runs the full warm-hub turn through to a success terminal (orb releases)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s()) // a real utterance — passes the hub release gate
    h.driver.end() // finalize + commit + hubCommitAccepted (warm)
    expect(h.hub.calls.commitTurn).toHaveLength(1)

    const ev = h.hub.events()
    ev.onSpeakingStart?.() // providerResponseStarted + playbackStarted
    ev.onTurnDone?.(null) // providerTurnFinished
    ev.onSpeakingEnd?.() // playbackDrained -> terminal(success)

    // Terminal reached: the driver told the bar to drop back to its local orb.
    const last = h.states.at(-1)!
    expect(last.active).toBe(false)
    expect(h.hub.calls.didTerminate).toHaveLength(1)
  })
})

// ---- (c) projection carries orb state -------------------------------------

describe('orb projection (main -> bar)', () => {
  it('a capture chunk carries a non-zero orb level while listening', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.states.length = 0
    h.capture.feed(loud())
    const s = h.states.at(-1)!
    expect(s.active).toBe(true)
    expect(s.isListening).toBe(true)
    expect(s.orbLevel).toBeGreaterThan(0)
  })

  // Regression (2026-07-18 round 2, "visualizer maxes out a lot" live finding):
  // the published orbLevel must follow the capture's streamed ~30Hz 64ms-window
  // levels lane once it delivers — NOT the 256ms chunk peaks, which bridge
  // every inter-syllable dip and held the bars at syllable peaks (4Hz).
  it('the streamed levels lane owns orbLevel once it delivers (chunk peak = first-frames fallback only)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    // Before any levels frame: the chunk-peak fallback publishes (first-frames coverage).
    h.states.length = 0
    h.capture.feed(loud())
    expect(h.states.at(-1)!.orbLevel).toBeGreaterThan(0.4) // peak of ±16000 ≈ 0.49
    // The levels lane delivers — it owns the published level from now on…
    h.capture.feedLevel(0.12)
    expect(h.states.at(-1)!.orbLevel).toBeCloseTo(0.12, 5)
    // …and a later LOUD chunk no longer overrides an inter-syllable dip.
    h.capture.feedLevel(0.03)
    h.capture.feed(loud())
    expect(h.states.at(-1)!.orbLevel).toBeCloseTo(0.03, 5)
  })

  it('a silent chunk projects a zero orb level', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.states.length = 0
    h.capture.feed(new Int16Array([0, 0, 0, 0]))
    expect(h.states.at(-1)!.orbLevel).toBe(0)
  })
})

// ---- (d) barge-in routes through the existing interrupt channel -----------

describe('barge-in', () => {
  it('every begin fires the interrupt seam (cascade/TTS barge-in)', () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    expect(h.spies.interruptPlayback).toHaveBeenCalledWith(null)
  })

  it('a superseding hold begins the hub turn interrupting:true', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.driver.begin({ backfillMs: 0 }) // a second hold while the first still owns the turn
    expect(h.hub.calls.beginTurn.at(-1)!.interrupting).toBe(true)
  })
})

// ---- chat recording (INV-CHAT-1: a hub turn lands in the one timeline) ------

describe('chat recording', () => {
  const finishTurn = (h: Harness): void => {
    const ev = h.hub.events()
    h.capture.feed(voiced1s()) // pass the hub release gate so the commit path runs
    h.driver.end()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.() // playbackDrained -> terminal(success)
  }

  it('records a completed hub turn exactly once (append, never re-answers)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    ev.onInputTranscript?.('what time is it', true, null)
    ev.onAssistantText?.("it's noon", false, null)
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith(
      'what time is it',
      "it's noon",
      false,
      expect.any(String)
    )
    // The per-press turnId is threaded through as the record's idempotency key, and
    // the same id is marked "seen" so the seed refresh won't reconnect for it.
    const recordedTurnId = h.spies.onRecordTurn.mock.calls[0][3]
    expect(h.hub.calls.seedProduced).toContain(recordedTurnId)
    // Append-only: a hub turn must NOT go through the cascade send (no LLM re-answer).
    expect(h.spies.onFinalText).not.toHaveBeenCalled()
  })

  it('an empty final assistant marker does not wipe the accumulated reply', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    ev.onInputTranscript?.('capital of france', true, null)
    ev.onAssistantText?.('Paris', false, null) // streamed delta
    ev.onAssistantText?.('', true, null) // OpenAI GA empty-final marker
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith(
      'capital of france',
      'Paris',
      false,
      expect.any(String)
    )
  })

  it('barge-in records the interrupted turn once, then the successor — no double-record', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    // Turn 1: a partial reply, then a barge-in supersedes it.
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    ev.onInputTranscript?.('turn one', true, null)
    ev.onAssistantText?.('partial reply', false, null)
    h.driver.begin({ backfillMs: 0 }) // barge-in
    await flush()
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
    expect(h.spies.onRecordTurn).toHaveBeenLastCalledWith(
      'turn one',
      'partial reply',
      true,
      expect.any(String)
    )
    // Turn 2 completes normally.
    ev.onInputTranscript?.('turn two', true, null)
    ev.onAssistantText?.('full reply', false, null)
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(2)
    expect(h.spies.onRecordTurn).toHaveBeenLastCalledWith(
      'turn two',
      'full reply',
      false,
      expect.any(String)
    )
    // Each turn carries a DISTINCT id (the barge-in successor is a new press).
    const [firstId, secondId] = h.spies.onRecordTurn.mock.calls.map((c) => c[3])
    expect(firstId).not.toEqual(secondId)
  })

  it('does not record a cascade turn via onRecordTurn (no accumulated hub reply)', async () => {
    const h = makeDriver({ pttHubEnabled: true, transcript: 'take a note' })
    h.hub.setAvailability(false) // omniSTT cascade route
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s()) // a real utterance — passes the release gate
    h.driver.end()
    await flush()
    await flush()
    expect(h.spies.onRecordTurn).not.toHaveBeenCalled()
    // cascade records via send, threading the per-press turnId as the shared key.
    expect(h.spies.onFinalText).toHaveBeenCalledWith('take a note', expect.any(String))
  })

  it('records at provider turn-done, BEFORE the spoken reply finishes playing (Mac parity)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    ev.onInputTranscript?.('what time is it', true, null)
    ev.onAssistantText?.("it's noon", false, null)
    h.capture.feed(voiced1s())
    h.driver.end()
    ev.onSpeakingStart?.() // playback begins (lease held) — the reply is still speaking
    ev.onTurnDone?.(null) // provider finished GENERATING (playback NOT yet drained)

    // Recorded NOW — not held until playbackDrained. This is the whole fix: on a long
    // reply the message pair must land while the audio is still playing.
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith(
      'what time is it',
      "it's noon",
      false,
      expect.any(String)
    )

    // The later playback-drain terminal must NOT double-record (INV-CHAT-1 exactly-once
    // via the turnRecorded dedup).
    ev.onSpeakingEnd?.() // playbackDrained -> terminal(success)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
  })

  it('records a turn with an empty assistant reply (one side present) exactly once', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    ev.onInputTranscript?.('did it work', true, null)
    // No assistant text this turn (the provider produced audio/no reply text).
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith('did it work', '', false, expect.any(String))
  })

  it('records a turn with an empty user transcript (quiet hold) exactly once', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    const ev = h.hub.events()
    // No input transcription (near-silent hold) — only a spoken reply.
    ev.onAssistantText?.('here you go', false, null)
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(1)
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith('', 'here you go', false, expect.any(String))
  })

  it('does not record a both-empty turn', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    finishTurn(h) // no transcript, no reply
    expect(h.spies.onRecordTurn).not.toHaveBeenCalled()
  })
})

// ---- system-audio duck (A5 §5) --------------------------------------------

describe('system-audio duck', () => {
  it('ducks other apps at capture start', () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    expect(h.spies.muteForCapture).toHaveBeenCalledTimes(1)
  })

  it('restores exactly once on the turn terminal', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    const ev = h.hub.events()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.()
    expect(h.spies.restoreSystemAudio).toHaveBeenCalledTimes(1)
  })
})

// ---- cascade route (flag on, hub unavailable) -----------------------------

describe('cascade route (omniSTT)', () => {
  it('flag on but hub unavailable → omniSTT: no hub, transcribe on release, text to chat', async () => {
    const h = makeDriver({ pttHubEnabled: true, transcript: 'take a note' })
    h.hub.setAvailability(false) // hub not warm/available -> selectPttRoute -> omniSTT
    h.driver.begin({ backfillMs: 0 })
    await flush()
    expect(h.hub.calls.beginTurn).toHaveLength(0)
    h.capture.feed(voiced1s())
    h.driver.end()
    await flush()
    await flush()
    expect(h.spies.transcribe).toHaveBeenCalledTimes(1)
    expect(h.spies.onFinalText).toHaveBeenCalledWith('take a note', expect.any(String))
    expect(h.states.at(-1)!.active).toBe(false) // turn ended, orb idle
  })
})

// ---- hub warm-wait -> cascade fallback -------------------------------------

describe('warm-wait fallback', () => {
  it('a cold press that loses the 1 s hubWarm race hands off to the cascade', async () => {
    const h = makeDriver({ pttHubEnabled: true, transcript: 'fallback text' })
    h.hub.setAvailability(false, true) // available (session exists) but not warm -> hubWarmWait
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s()) // a real utterance — passes the hub release gate
    h.driver.end() // finalize + hubCommitDeferred (not warm)
    // The hub controller would fire onCascadeHandoff off handoffWarmWaitToCascade;
    // simulate the reducer firing the 1 s hubWarm deadline, then the controller's handoff.
    h.scheduler.fire('hubWarm')
    h.hub.events().onCascadeHandoff?.({ frames: [pcm16ToBytes(voiced1s())], committed: true })
    await flush()
    await flush()
    expect(h.spies.transcribe).toHaveBeenCalled()
    expect(h.spies.onFinalText).toHaveBeenCalledWith('fallback text', expect.any(String))
  })
})

// ---- cascade release gate (the empty-first-press field bug, 2026-07) --------
// The first PTT press after idle can capture ZERO samples (mic spin-up after a
// long idle outlasts the hold), and the cascade lane POSTed that empty buffer →
// backend 400 "No audio data provided" with no user feedback. The driver must
// gate on the captured audio (macOS finalize silence-gate parity): never POST
// empty/too-short audio, and never end such a turn silently.

describe('cascade release gate (empty / too-short / silent captures)', () => {
  it('an empty capture (cold-mic first press) never POSTs and shows "Hold longer to record"', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(false) // omniSTT cascade route
    h.driver.begin({ backfillMs: 0 })
    await flush()
    // No chunks ever arrive (mic still spinning up for the whole hold).
    h.driver.end()
    await flush()
    expect(h.spies.transcribe).not.toHaveBeenCalled() // the zero-byte POST is gone
    expect(h.spies.onFinalText).not.toHaveBeenCalled()
    // Not silent: the reducer terminal carries Mac's too-short hint to the bar.
    expect(h.states.some((s) => s.hint === 'Hold longer to record')).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false) // turn ended, orb idle
  })

  it('a too-short capture (a few frames under 0.35s) is hinted, not POSTed', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(false)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(loud()) // 4 samples ≪ MIN_TOTAL_AUDIO_SEC
    h.driver.end()
    await flush()
    expect(h.spies.transcribe).not.toHaveBeenCalled()
    expect(h.states.some((s) => s.hint === 'Hold longer to record')).toBe(true)
  })

  it('a real hold with no speech (quiet room) is discarded quietly — no POST, no hint', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(false)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    // 1s of low-level room noise: total ≥ 0.35s, peak above the dead-mic floor,
    // but nothing voiced — Mac discards silence without ceremony (STT models
    // hallucinate phrases from silence, so it must never be sent).
    h.capture.feed(new Int16Array(16000).fill(100))
    h.driver.end()
    await flush()
    expect(h.spies.transcribe).not.toHaveBeenCalled()
    expect(h.states.every((s) => s.hint === '')).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false)
  })

  it('a warm-wait handoff whose hub buffered nothing is hinted, not POSTed', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(false, true) // hubWarmWait route
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.driver.end() // released before any audio arrived
    h.scheduler.fire('hubWarm')
    h.hub.events().onCascadeHandoff?.({ frames: [], committed: true })
    await flush()
    expect(h.spies.transcribe).not.toHaveBeenCalled()
    expect(h.states.some((s) => s.hint === 'Hold longer to record')).toBe(true)
  })
})

// ---- cancel ---------------------------------------------------------------

describe('cancel', () => {
  it('cancel terminates the turn and idles the orb', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.driver.cancel()
    expect(h.hub.calls.cancelTurn).toHaveLength(1) // reducer cancelHub -> host -> hub.cancelTurn
    expect(h.states.at(-1)!.active).toBe(false)
  })
})

// ---- pure PCM helpers ------------------------------------------------------

describe('pcm helpers', () => {
  it('pcmPeakLevel normalizes the peak to [0,1]', () => {
    expect(pcmPeakLevel(new Int16Array([0, 0]))).toBe(0)
    expect(pcmPeakLevel(Int16Array.from([16384, -32768]))).toBeCloseTo(1, 5)
  })

  it('concatInt16 joins frames in order', () => {
    const out = concatInt16([Int16Array.from([1, 2]), Int16Array.from([3])])
    expect(Array.from(out)).toEqual([1, 2, 3])
  })

  it('pcm16ToBytes / bytesToPcm16 round-trip samples', () => {
    const src = Int16Array.from([1, -1, 1000, -1000])
    expect(Array.from(bytesToPcm16(pcm16ToBytes(src)))).toEqual(Array.from(src))
  })

  it('resamplePcm16 upsamples 16k->24k to a 1.5x length and returns the same ref when equal', () => {
    const src = Int16Array.from([0, 100, 200, 400])
    expect(resamplePcm16(src, 16000, 16000)).toBe(src)
    expect(resamplePcm16(src, 16000, 24000).length).toBe(6)
  })
})

// ---- post-commit provider death surfaces a hint (A7c follow-up #1) ----------
// A committed hub turn whose provider dies mid-reply used to end SILENTLY: the
// reducer computed a "Voice response failed" hint but `VoiceHubBarState` had no
// hint field, so `emit` dropped it and the orb just idled. These pin the plumbing
// fix — the hint now reaches the bar and auto-clears on the hintVisibility deadline.

describe('post-commit provider death (A7c follow-up #1)', () => {
  const driveToProviderDeath = (h: Harness): void => {
    h.hub.setAvailability(true) // warm hub → route = hub
    h.driver.begin({ backfillMs: 0 })
    // Socket ready → the release commits into awaitingResponse.
    h.hub.events().onConnected?.('sess' as VoiceSessionID)
    h.capture.feed(voiced1s()) // pass the hub release gate (onChunk is wired at begin)
    h.driver.end()
    // The provider dies mid-reply (post-commit): the controller surfaces onError.
    h.hub.events().onError?.({
      reason: 'websocket closed (1008)',
      retryable: true,
      aliveForMs: 5000
    })
  }

  it("projects the reducer's terminal hint into VoiceHubBarState.hint (not a silent idle)", async () => {
    const h = makeDriver({ pttHubEnabled: true })
    driveToProviderDeath(h)

    const last = h.states.at(-1)!
    expect(last.active).toBe(false) // the orb dropped to idle...
    expect(last.hint).toBe('Voice response failed — try again') // ...but the hint rode along
    expect(h.hub.calls.didTerminate).toHaveLength(1)
  })

  it("clears the hint when the reducer's hintVisibility deadline fires (auto-dismiss)", async () => {
    const h = makeDriver({ pttHubEnabled: true })
    driveToProviderDeath(h)
    expect(h.states.at(-1)!.hint).toBe('Voice response failed — try again')

    h.scheduler.fire('hintVisibility')
    expect(h.states.at(-1)!.hint).toBe('')
  })
})

// ---- (e) PR-C: the hub tool loop ------------------------------------------
//
// A spoken tool request is dispatched IN-PROCESS via the injected executeTool seam
// (production = the shared executeHostTool over IPC) and its result relayed back to
// the provider keyed by callId, gated by the turn epoch so a superseded turn's late
// result is dropped. Parallel calls each register; the turn defers until all resolve.

/** Drive a warm-hub turn to the point the provider can request a tool (awaitingResponse
 *  after end() → hubCommitDeferred, exactly as the success-terminal test does). */
async function driveToAwaitingResponse(h: Harness): Promise<void> {
  h.hub.setAvailability(true)
  h.driver.begin({ backfillMs: 0 })
  await flush()
  h.capture.feed(voiced1s()) // pass the hub release gate
  h.driver.end()
}

describe('hub tool loop (PR-C)', () => {
  it('dispatches a spoken tool request in-process and relays the result keyed by callId', async () => {
    let resolveTool!: (out: string) => void
    const executeTool = vi.fn(
      (_name: string, _args: string) => new Promise<string>((r) => (resolveTool = r))
    )
    const h = makeDriver({ pttHubEnabled: true, executeTool })
    await driveToAwaitingResponse(h)

    h.hub
      .events()
      .onToolRequest?.({ name: 'list_agent_sessions', callId: 'call-1', argumentsJSON: '{}' }, null)
    // The name + raw args string are forwarded verbatim to the host dispatcher.
    expect(executeTool).toHaveBeenCalledWith('list_agent_sessions', '{}')
    // Nothing is relayed until the tool resolves.
    expect(h.hub.calls.sendToolResult).toHaveLength(0)

    resolveTool('{"ok":true,"sessions":[]}')
    await flush()
    expect(h.hub.calls.sendToolResult).toEqual([
      { callId: 'call-1', name: 'list_agent_sessions', output: '{"ok":true,"sessions":[]}' }
    ])

    // After the tool, the model speaks and the turn completes normally.
    const ev = h.hub.events()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.()
    expect(h.hub.calls.didTerminate).toHaveLength(1)
  })

  it('drops a stale tool result when the turn was superseded (turn-epoch gate)', async () => {
    let resolveTool!: (out: string) => void
    const executeTool = vi.fn(() => new Promise<string>((r) => (resolveTool = r)))
    const h = makeDriver({ pttHubEnabled: true, executeTool })
    await driveToAwaitingResponse(h)

    h.hub
      .events()
      .onToolRequest?.({ name: 'list_agent_sessions', callId: 'call-1', argumentsJSON: '{}' }, null)
    // Barge-in: a new hold supersedes the turn while the tool is still running.
    h.driver.begin({ backfillMs: 0 })
    await flush()

    resolveTool('{"ok":true}')
    await flush()
    // The stale result is neither relayed to the provider nor dispatched to the reducer.
    expect(h.hub.calls.sendToolResult).toHaveLength(0)
  })

  it('supports parallel tool calls — each result relayed by its own callId', async () => {
    const resolvers = new Map<string, (out: string) => void>()
    const executeTool = vi.fn((name: string) => new Promise<string>((r) => resolvers.set(name, r)))
    const h = makeDriver({ pttHubEnabled: true, executeTool })
    await driveToAwaitingResponse(h)

    const ev = h.hub.events()
    ev.onToolRequest?.({ name: 'list_agent_sessions', callId: 'c1', argumentsJSON: '{}' }, null)
    ev.onToolRequest?.(
      { name: 'get_agent_run', callId: 'c2', argumentsJSON: '{"runId":"r"}' },
      null
    )
    expect(executeTool).toHaveBeenCalledTimes(2)

    resolvers.get('get_agent_run')!('{"ok":true,"run":{}}')
    resolvers.get('list_agent_sessions')!('{"ok":true}')
    await flush()

    expect(h.hub.calls.sendToolResult).toHaveLength(2)
    expect(h.hub.calls.sendToolResult.map((c) => c.callId).sort()).toEqual(['c1', 'c2'])
  })

  it('with no executor wired, satisfies the provider so the turn cannot hang', async () => {
    const h = makeDriver({ pttHubEnabled: true }) // no executeTool
    await driveToAwaitingResponse(h)

    h.hub.events().onToolRequest?.({ name: 'x', callId: 'c1', argumentsJSON: '{}' }, null)
    expect(h.hub.calls.sendToolResult).toHaveLength(1)
    expect(h.hub.calls.sendToolResult[0].output).toMatch(/^Error:/)
  })
})

// ---- hub release gate (the 2026-07-18 short-press wedge) --------------------
// A 220–350 ms press (recordable only since the Mac-parity 220 ms threshold) on
// the HUB lane used to commit a near-empty turn to the provider — which may never
// answer — and a release that beat the capture spin-up committed literally zero
// audio. The hub lane now mirrors the cascade release gate exactly: such turns
// ALWAYS finalize deterministically at release, ownership is freed, and the warm
// socket is kept for the next press.

describe('hub release gate (short/empty hub-owned captures)', () => {
  it('a too-short hub press never commits: tooShort terminal, socket kept, hint, next press fresh', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(loud()) // 4 samples ≪ MIN_TOTAL_AUDIO_SEC
    h.driver.end()

    // Never committed to the provider; the hub turn was abandoned (socket kept)
    // and per-turn ownership released.
    expect(h.hub.calls.commitTurn).toHaveLength(0)
    expect(h.hub.calls.cancelTurn).toHaveLength(1)
    expect(h.hub.calls.didTerminate).toHaveLength(1)
    // Mac's cascade hint, not a silent discard and never a hang.
    expect(h.states.some((s) => s.hint === 'Hold longer to record')).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false)

    // The machine is free: the next press starts a fresh hub turn immediately.
    h.driver.begin({ backfillMs: 0 })
    expect(h.hub.calls.beginTurn).toHaveLength(2)
    expect(h.states.at(-1)!.isListening).toBe(true)
  })

  it('release racing capture spin-up (zero samples) finalizes tooShort and disposes the orphan mic', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    // Release BEFORE the capture promise resolves — the exact wedged-press shape.
    h.driver.end()

    expect(h.hub.calls.commitTurn).toHaveLength(0)
    expect(h.states.some((s) => s.hint === 'Hold longer to record')).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false)

    // The late-resolving capture is an orphan and must be disposed, not leaked.
    await flush()
    expect(h.capture.cap.dispose).toHaveBeenCalled()

    // Next press starts fresh.
    h.driver.begin({ backfillMs: 0 })
    expect(h.hub.calls.beginTurn).toHaveLength(2)
    expect(h.states.at(-1)!.isListening).toBe(true)
  })

  it('a real hub hold with no speech is discarded quietly (silentRejected, no hint)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    // 1 s of low-level room noise: total ≥ 0.35 s, peak above the dead-mic floor,
    // nothing voiced — mirror the cascade lane's quiet discard.
    h.capture.feed(new Int16Array(16000).fill(100))
    h.driver.end()

    expect(h.hub.calls.commitTurn).toHaveLength(0)
    expect(h.states.every((s) => s.hint === '')).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false)
  })

  it('a voiced hub press still commits (no regression on real speech)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    expect(h.hub.calls.commitTurn).toHaveLength(1)
  })
})

// ---- release watchdog (no turn may hold ownership forever) ------------------
// Belt-and-braces above the reducer's own deadlines: if the deadline machinery
// itself is broken (the wedge class — e.g. a collaborator throw skipped the
// scheduling effect before the coordinator contained throws), a turn stuck in a
// pre-response phase after release is force-finalized and the machine freed.

describe('release watchdog', () => {
  it('force-finalizes a turn stuck pre-response after release; the next press starts fresh', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      const h = makeDriver({ pttHubEnabled: true })
      h.hub.setAvailability(false) // omniSTT cascade route
      // The batch STT hangs forever AND (wedge class) the machine's transcription
      // deadline never fires (the manual scheduler stands in for a lost timer).
      h.spies.transcribe.mockImplementation(() => new Promise<string>(() => {}))
      h.driver.begin({ backfillMs: 0 })
      await flush()
      h.capture.feed(voiced1s())
      h.driver.end() // -> transcriptionStarted, phase stays 'finalizing'
      expect(h.watchdog.armed).toBe(true)
      expect(h.watchdog.cancelled).toBe(false)

      h.watchdog.fire()

      // Ownership fully released: hub per-turn state, orb idle, hint surfaced.
      expect(h.hub.calls.didTerminate.length).toBeGreaterThan(0)
      const last = h.states.at(-1)!
      expect(last.active).toBe(false)
      expect(last.hint).toBe(RELEASE_WATCHDOG_HINT)

      // The machine is free: a new press begins a fresh turn.
      h.driver.begin({ backfillMs: 0 })
      expect(h.states.at(-1)!.isListening).toBe(true)
      expect(h.states.at(-1)!.active).toBe(true)
    } finally {
      errSpy.mockRestore()
    }
  })

  it('never fires into a turn that advanced past finalize (long replies untouched)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end() // committed -> awaitingResponse (reducer deadlines own it now)

    h.watchdog.fire()

    // Nothing was forced: the turn is still live and un-hinted.
    expect(h.states.at(-1)!.active).toBe(true)
    expect(h.hub.calls.didTerminate).toHaveLength(0)
    expect(h.states.every((s) => s.hint !== RELEASE_WATCHDOG_HINT)).toBe(true)

    // And the turn still completes normally afterwards.
    const ev = h.hub.events()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.()
    expect(h.states.at(-1)!.active).toBe(false)
    expect(h.hub.calls.didTerminate).toHaveLength(1)
  })

  it('is cancelled by a normal terminal (no stray force-finalize after success)', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    const ev = h.hub.events()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.() // -> terminal(success)
    expect(h.watchdog.cancelled).toBe(true)
  })

  it('an armed watchdog from a superseded turn never fires into its successor', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end() // arms the watchdog; turn now awaitingResponse
    const staleFire = h.watchdog.fire

    h.driver.begin({ backfillMs: 0 }) // barge-in successor (cancels + re-owns)
    await flush()
    staleFire() // the old handle firing late must be inert

    expect(h.states.at(-1)!.active).toBe(true)
    expect(h.states.every((s) => s.hint !== RELEASE_WATCHDOG_HINT)).toBe(true)
  })
})

// ---- dispose (resetVoicePlane) --------------------------------------------

describe('dispose (resetVoicePlane)', () => {
  it('mid-recording: releases capture + socket + mute, publishes idle, and is inert after', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())

    h.driver.dispose()

    expect(h.capture.cap.dispose).toHaveBeenCalled()
    expect(h.hub.calls.teardown).toBe(1)
    expect(h.spies.restoreSystemAudio).toHaveBeenCalled()
    const last = h.states.at(-1)!
    expect(last.active).toBe(false)
    expect(last.isListening).toBe(false)

    // A disposed driver never runs again: no new capture, no warm, no hub turn.
    h.driver.begin({ backfillMs: 0 })
    expect(h.capture.start).toHaveBeenCalledTimes(1)
    h.driver.warm()
    expect(h.hub.calls.ensureWarm).toBe(0)
  })

  it('mid-reply (playing): stops playback and still releases everything', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    const ev = h.hub.events()
    ev.onSpeakingStart?.()

    h.driver.dispose()

    // The cleanup terminal's stopPlayback effect reached the interrupt seam.
    expect(h.spies.interruptPlayback).toHaveBeenCalled()
    expect(h.hub.calls.teardown).toBe(1)
    expect(h.states.at(-1)!.active).toBe(false)
  })

  it('post-release (watchdog armed): dispose cancels the watchdog and frees the turn', async () => {
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    expect(h.watchdog.armed).toBe(true)

    h.driver.dispose()

    expect(h.watchdog.cancelled).toBe(true)
    expect(h.states.at(-1)!.active).toBe(false)
  })

  it('idle: dispose is safe and idempotent', () => {
    const h = makeDriver({ pttHubEnabled: true })
    expect(() => {
      h.driver.dispose()
      h.driver.dispose()
    }).not.toThrow()
    expect(h.hub.calls.teardown).toBe(1)
  })

  it('after a reset, a FRESH driver runs a full turn to success (working plane)', async () => {
    const old = makeDriver({ pttHubEnabled: true })
    old.hub.setAvailability(true)
    old.driver.begin({ backfillMs: 0 })
    await flush()
    old.driver.dispose()

    // The host swaps in a fresh driver (VoiceHubDriverHost.onVoicePlaneReset).
    const h = makeDriver({ pttHubEnabled: true })
    h.hub.setAvailability(true)
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.capture.feed(voiced1s())
    h.driver.end()
    const ev = h.hub.events()
    ev.onSpeakingStart?.()
    ev.onTurnDone?.(null)
    ev.onSpeakingEnd?.()
    expect(h.states.at(-1)!.active).toBe(false)
    expect(h.spies.onRecordTurn).not.toHaveBeenCalledWith('', '', expect.anything(), expect.anything())
  })
})
