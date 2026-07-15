// Hermetic tests for the warm-hub PTT DRIVER (A5 PR-6b) — the cross-window ON-path.
// Every collaborator is a fake, so no window, WebSocket, mic, or pcmPlayer is
// touched. Covers the four brief-required cases and the core turn lifecycles.
import { describe, it, expect, vi } from 'vitest'
import {
  VoiceHubTurnDriver,
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
    ensureWarm: 0
  }
  const hub = {
    isWarm: () => warm,
    isAvailable: () => available,
    requiredInputSampleRate: () => (warm || available ? 24000 : null),
    ensureWarm: () => {
      calls.ensureWarm++
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
    voiceTurnDidTerminate: (turnID: VoiceTurnID) => calls.didTerminate.push(turnID)
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
    calls
  }
}

function makeFakeCapture() {
  let onChunk: ((pcm: Int16Array) => void) | undefined
  const cap: PttCapture = {
    analyser: { getByteFrequencyData: () => {}, getOrbLevel: () => 0 },
    drain: () => Promise.resolve(new Int16Array(0)),
    dispose: vi.fn()
  }
  const start = vi.fn((opts: PttCaptureOptions): Promise<PttCapture> => {
    onChunk = opts.onChunk
    return Promise.resolve(cap)
  })
  return { start, feed: (pcm: Int16Array) => onChunk?.(pcm), cap }
}

type Harness = {
  driver: VoiceHubTurnDriver
  hub: ReturnType<typeof makeFakeHub>
  capture: ReturnType<typeof makeFakeCapture>
  scheduler: ManualScheduler
  states: VoiceHubBarState[]
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

function makeDriver(opts: { pttHubEnabled?: boolean; transcript?: string } = {}): Harness {
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
  const deps: VoiceHubTurnDriverDeps = {
    createHub: hub.factory,
    interruptPlayback: spies.interruptPlayback,
    publishState: (s) => states.push(s),
    startCapture: capture.start,
    transcribe: spies.transcribe,
    onFinalText: spies.onFinalText,
    onRecordTurn: spies.onRecordTurn,
    muteForCapture: spies.muteForCapture,
    restoreSystemAudio: spies.restoreSystemAudio,
    trackEvent: spies.trackEvent,
    prefs: () => ({ pttHubEnabled: opts.pttHubEnabled }),
    scheduler,
    mintTurnID: () => `turn-${++turnSeq}` as VoiceTurnID,
    mintCaptureID: () => ++turnSeq as unknown as VoiceCaptureID,
    now: () => (clock += 1000) // strictly increasing so the orb throttle never blocks
  }
  return { driver: new VoiceHubTurnDriver(deps), hub, capture, scheduler, states, spies }
}

const flush = (): Promise<void> => Promise.resolve().then(() => {})
const loud = (): Int16Array => Int16Array.from([0, 16000, -16000, 8000])

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
    h.capture.feed(loud())
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
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith('what time is it', "it's noon", false)
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
    expect(h.spies.onRecordTurn).toHaveBeenCalledWith('capital of france', 'Paris', false)
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
    expect(h.spies.onRecordTurn).toHaveBeenLastCalledWith('turn one', 'partial reply', true)
    // Turn 2 completes normally.
    ev.onInputTranscript?.('turn two', true, null)
    ev.onAssistantText?.('full reply', false, null)
    finishTurn(h)
    expect(h.spies.onRecordTurn).toHaveBeenCalledTimes(2)
    expect(h.spies.onRecordTurn).toHaveBeenLastCalledWith('turn two', 'full reply', false)
  })

  it('does not record a cascade turn via onRecordTurn (no accumulated hub reply)', async () => {
    const h = makeDriver({ pttHubEnabled: true, transcript: 'take a note' })
    h.hub.setAvailability(false) // omniSTT cascade route
    h.driver.begin({ backfillMs: 0 })
    await flush()
    h.driver.end()
    await flush()
    await flush()
    expect(h.spies.onRecordTurn).not.toHaveBeenCalled()
    expect(h.spies.onFinalText).toHaveBeenCalledWith('take a note') // cascade records via send
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
    h.capture.feed(loud())
    h.driver.end()
    await flush()
    await flush()
    expect(h.spies.transcribe).toHaveBeenCalledTimes(1)
    expect(h.spies.onFinalText).toHaveBeenCalledWith('take a note')
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
    h.capture.feed(loud())
    h.driver.end() // finalize + hubCommitDeferred (not warm)
    // The hub controller would fire onCascadeHandoff off handoffWarmWaitToCascade;
    // simulate the reducer firing the 1 s hubWarm deadline, then the controller's handoff.
    h.scheduler.fire('hubWarm')
    h.hub.events().onCascadeHandoff?.({ frames: [pcm16ToBytes(loud())], committed: true })
    await flush()
    await flush()
    expect(h.spies.transcribe).toHaveBeenCalled()
    expect(h.spies.onFinalText).toHaveBeenCalledWith('fallback text')
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
