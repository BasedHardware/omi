import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { VoiceProvider } from '../sessionMachine'
import type { VoiceSessionID, VoiceTurnID } from '../turn/voiceTurnMachine'
import type { HubSession, HubSessionEvents, HubBargeInStrategy, HubProvider } from './hubSession'

// The real provider sessions (imported at hubController's module top) transitively
// pull in pcmPlayer's AudioWorklet `?worker&url` asset, which does not resolve in
// the node test env. Stub it; the controller injects a fake session anyway.
vi.mock('../pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

// Spy the shared fallback-telemetry helper so the one fail-open path (hub → cascade
// on the 1 s warm timeout) is asserted exactly, with no new counter invented.
vi.mock('../../analytics', () => ({ trackEvent: vi.fn() }))

import { trackEvent } from '../../analytics'
import { HubController, type HubControllerEvents } from './hubController'
import { HUB_IDLE_TEARDOWN_THRESHOLD_MS } from './hubClose'

// A fake provider session: records every frame-level call and lets the test drive
// the connect / error edges deterministically. Buffering is the controller's job,
// so `appendAudio` here only ever sees post-connect frames (the controller
// withholds during warm-wait).
class FakeSession implements HubSession {
  readonly provider: HubProvider = 'openai'
  readonly requiredInputSampleRate = 24000
  readonly bargeInStrategy: HubBargeInStrategy = 'inSessionCancel'

  warm = false
  appended: Uint8Array[] = []
  committed = 0
  cancelled = 0
  begun: { interrupting: boolean }[] = []
  toreDown = 0
  toolResults: { callId: string; output: string }[] = []
  private resolveWarm: (() => void) | null = null
  private rejectWarm: ((e: Error) => void) | null = null

  constructor(
    readonly sessionID: VoiceSessionID,
    readonly events: HubSessionEvents
  ) {}

  ensureWarm(): Promise<void> {
    if (this.warm) return Promise.resolve()
    return new Promise((resolve, reject) => {
      this.resolveWarm = resolve
      this.rejectWarm = reject
    })
  }
  /** Test-only: mark ready, fire onConnected (controller flushes here), resolve. */
  connect(): void {
    this.warm = true
    this.events.onConnected?.(this.sessionID)
    this.resolveWarm?.()
    this.resolveWarm = null
    this.rejectWarm = null
  }
  /** Test-only: a fatal mid-session error. `closeCode` mirrors a real WS close code
   *  (BaseHubSession threads it through), so the A7c classifier sees a genuine 1008.
   *  Rejects the pending warm promise exactly like BaseHubSession.handleError, so the
   *  controller's in-flight `warming` clears and a re-warm can rebuild. */
  fail(message: string, retryable = true, closeCode?: number): void {
    this.warm = false
    this.events.onError?.(message, retryable, closeCode)
    this.rejectWarm?.(new Error(message))
    this.rejectWarm = null
    this.resolveWarm = null
  }
  isWarm(): boolean {
    return this.warm
  }
  beginTurn(opts: { interrupting?: boolean } = {}): void {
    this.begun.push({ interrupting: opts.interrupting ?? false })
  }
  appendAudio(pcm: Uint8Array): void {
    this.appended.push(pcm)
  }
  commitTurn(): void {
    this.committed += 1
  }
  cancelTurn(): void {
    this.cancelled += 1
  }
  sendToolResult(callId: string, _name: string, output: string): void {
    this.toolResults.push({ callId, output })
  }
  teardown(): void {
    this.toreDown += 1
    this.warm = false
  }
}

const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
const t1 = 'turn-1' as VoiceTurnID
const t2 = 'turn-2' as VoiceTurnID
const SID = 'sess-1' as VoiceSessionID
const frame = (n: number): Uint8Array => new Uint8Array([n])

type Harness = {
  controller: HubController
  events: Record<keyof HubControllerEvents, ReturnType<typeof vi.fn>>
  mintToken: ReturnType<typeof vi.fn>
  createSession: ReturnType<typeof vi.fn>
  getSession: () => FakeSession
  now: { value: number }
  /** True while a reconnect backoff is armed (the injected fake timer is pending). */
  pendingReconnect: () => boolean
  /** Fire the pending reconnect backoff (drives the controller's self re-warm). */
  fireReconnect: () => void
}

function harness(opts?: { provider?: VoiceProvider; instructions?: string }): Harness {
  const events = {
    onConnected: vi.fn(),
    onError: vi.fn(),
    onInputTranscript: vi.fn(),
    onAssistantText: vi.fn(),
    onSpeakingStart: vi.fn(),
    onSpeakingEnd: vi.fn(),
    onToolRequest: vi.fn(),
    onTurnDone: vi.fn(),
    onCascadeHandoff: vi.fn()
  }
  let session: FakeSession | undefined
  const mintToken = vi.fn(async (_p: VoiceProvider) => 'ek_token')
  const createSession = vi.fn((spec: { provider: VoiceProvider; events: HubSessionEvents }) => {
    session = new FakeSession(SID, spec.events)
    return session
  })
  const now = { value: 1_000 }
  // Injected fake timer for the A7c reconnect backoff — never auto-fires, so tests are
  // deterministic and no real timer leaks between cases. scheduleReWarm coalesces on
  // `reconnectPending`, so at most one is armed at a time.
  const timers = new Map<number, () => void>()
  let timerSeq = 0
  const controller = new HubController({
    events,
    resolveProvider: () => opts?.provider ?? 'openai',
    buildInstructions: () => opts?.instructions ?? 'INSTRUCTIONS+CARD',
    mintToken,
    createSession,
    now: () => now.value,
    setTimer: (_ms, fire) => {
      const id = ++timerSeq
      timers.set(id, fire)
      return id
    },
    clearTimer: (h) => {
      timers.delete(h as number)
    }
  })
  return {
    controller,
    events,
    mintToken,
    createSession,
    getSession: () => {
      if (!session) throw new Error('session not created yet')
      return session
    },
    now,
    pendingReconnect: () => timers.size > 0,
    fireReconnect: () => {
      const entry = [...timers.entries()][0]
      if (entry === undefined) throw new Error('no pending reconnect timer')
      timers.delete(entry[0])
      entry[1]()
    }
  }
}

/** Warm the controller fully: mint → create → connect → resolved. */
async function warmed(h: Harness): Promise<void> {
  const p = h.controller.ensureWarm()
  await tick() // past the mint await → session created
  h.getSession().connect()
  await p
}

beforeEach(() => {
  vi.mocked(trackEvent).mockClear()
})

describe('HubController — ensureWarm (A8 provider + A9 instructions)', () => {
  it('resolves the effective provider, mints a token, and builds the session with the A9 instructions', async () => {
    const h = harness({ provider: 'gemini', instructions: 'PERSONA + <about_user>…' })
    const p = h.controller.ensureWarm()
    await tick()
    h.getSession().connect()
    const sid = await p

    expect(h.mintToken).toHaveBeenCalledExactlyOnceWith('gemini')
    expect(h.createSession).toHaveBeenCalledTimes(1)
    expect(h.createSession.mock.calls[0][0]).toMatchObject({
      provider: 'gemini',
      token: 'ek_token',
      instructions: 'PERSONA + <about_user>…'
    })
    expect(sid).toBe(SID)
    expect(h.controller.isWarm()).toBe(true)
    expect(h.events.onConnected).toHaveBeenCalledWith(SID)
  })

  it('is idempotent — a second warm on the same provider reuses the session, and concurrent warms coalesce', async () => {
    const h = harness()
    const a = h.controller.ensureWarm()
    const b = h.controller.ensureWarm() // concurrent → same in-flight promise
    await tick()
    h.getSession().connect()
    await Promise.all([a, b])

    // Already warm → no re-mint, no new session.
    const sid = await h.controller.ensureWarm()
    expect(sid).toBe(SID)
    expect(h.mintToken).toHaveBeenCalledTimes(1)
    expect(h.createSession).toHaveBeenCalledTimes(1)
  })
})

describe('HubController — warm-wait buffer', () => {
  it('withholds PCM during warm-wait and flushes it (in order) into the session on hub-ready', async () => {
    const h = harness()
    h.controller.beginTurn(t1)
    await tick() // session object created (still connecting)
    h.controller.appendAudio(t1, frame(1))
    h.controller.appendAudio(t1, frame(2))
    h.controller.commitTurn(t1)

    // Nothing reaches the session while it is still connecting.
    const s = h.getSession()
    expect(s.appended).toEqual([])
    expect(s.committed).toBe(0)

    s.connect() // hub wins the race
    expect(s.appended).toEqual([frame(1), frame(2)])
    expect(s.committed).toBe(1)
    expect(h.events.onCascadeHandoff).not.toHaveBeenCalled()
    // The hub WON — the fail-open telemetry must NOT fire on the happy flush; it is
    // reserved for the actual hub→cascade hand-off (guards against a telemetry leak
    // that would inflate the degraded-fallback rate on every successful warm turn).
    expect(trackEvent).not.toHaveBeenCalled()
  })

  it('hands the buffer to the cascade on the 1 s hubWarm timeout — the turn SURVIVES (not terminated, socket kept)', async () => {
    const h = harness()
    h.controller.beginTurn(t1)
    await tick()
    h.controller.appendAudio(t1, frame(1))
    h.controller.appendAudio(t1, frame(2))
    h.controller.commitTurn(t1)

    h.controller.handoffWarmWaitToCascade(t1)

    // The buffered PCM (and the released-before-ready flag) went to the cascade.
    expect(h.events.onCascadeHandoff).toHaveBeenCalledTimes(1)
    expect(h.events.onCascadeHandoff).toHaveBeenCalledWith({
      frames: [frame(1), frame(2)],
      committed: true
    })
    // Exactly the shared fallback event — closed enums, no new counter.
    expect(trackEvent).toHaveBeenCalledExactlyOnceWith('fallback_triggered', {
      component: 'ptt_cascade',
      from: 'hub',
      to: 'omni_stt',
      reason: 'hub_warm_timeout',
      outcome: 'degraded'
    })

    const s = h.getSession()
    // Turn survives: the warm socket is KEPT (only the hub side of the turn is
    // abandoned) and nothing terminated the turn.
    expect(s.toreDown).toBe(0)
    expect(s.cancelled).toBe(1)
    expect(h.controller.isAvailable()).toBe(true)

    // A second hand-off (or a late connect) does nothing more — buffer is gone.
    h.controller.handoffWarmWaitToCascade(t1)
    s.connect()
    expect(h.events.onCascadeHandoff).toHaveBeenCalledTimes(1)
    expect(s.appended).toEqual([])
    expect(s.committed).toBe(0)
  })

  it('discards the buffer on cancel — nothing is flushed and no hand-off fires', async () => {
    const h = harness()
    h.controller.beginTurn(t1)
    await tick()
    h.controller.appendAudio(t1, frame(1))

    h.controller.cancelTurn(t1)
    const s = h.getSession()
    expect(s.cancelled).toBe(1)

    s.connect() // a late connect must not resurrect the discarded audio
    expect(s.appended).toEqual([])
    expect(s.committed).toBe(0)
    expect(h.events.onCascadeHandoff).not.toHaveBeenCalled()
    expect(trackEvent).not.toHaveBeenCalled()
  })
})

describe('HubController — turn lifecycle', () => {
  it('voiceTurnDidTerminate releases per-turn state but KEEPS the warm socket for the next turn', async () => {
    const h = harness()
    await warmed(h)
    const s = h.getSession()

    h.controller.beginTurn(t1) // already warm → straight through
    h.controller.appendAudio(t1, frame(1))
    h.controller.commitTurn(t1)
    expect(s.appended).toEqual([frame(1)])
    expect(s.committed).toBe(1)

    h.controller.voiceTurnDidTerminate(t1)
    expect(s.toreDown).toBe(0)
    expect(h.controller.isWarm()).toBe(true)

    // The next turn reuses the SAME warm session (no re-mint, no new session).
    h.controller.beginTurn(t2)
    h.controller.appendAudio(t2, frame(2))
    expect(s.appended).toEqual([frame(1), frame(2)])
    expect(h.createSession).toHaveBeenCalledTimes(1)
    expect(h.mintToken).toHaveBeenCalledTimes(1)
  })

  it('the four turn primitives are turn-ID fenced — a stale-turn call is a no-op', async () => {
    const h = harness()
    await warmed(h)
    const s = h.getSession()
    h.controller.beginTurn(t1)

    // Every primitive carrying the WRONG (superseded) turn id is inert.
    h.controller.appendAudio(t2, frame(9))
    h.controller.commitTurn(t2)
    h.controller.cancelTurn(t2)
    h.controller.handoffWarmWaitToCascade(t2)
    h.controller.voiceTurnDidTerminate(t2)

    expect(s.appended).toEqual([])
    expect(s.committed).toBe(0)
    expect(s.cancelled).toBe(0)
    expect(h.events.onCascadeHandoff).not.toHaveBeenCalled()

    // The active turn still works after the stale calls were dropped.
    h.controller.appendAudio(t1, frame(1))
    h.controller.commitTurn(t1)
    expect(s.appended).toEqual([frame(1)])
    expect(s.committed).toBe(1)
  })

  it('a barge-in begin forwards the interrupting flag to the provider session', async () => {
    const h = harness()
    await warmed(h)
    const s = h.getSession()
    h.controller.beginTurn(t1)
    h.controller.voiceTurnDidTerminate(t1)
    h.controller.beginTurn(t2, { interrupting: true })
    expect(s.begun).toEqual([{ interrupting: false }, { interrupting: true }])
  })
})

describe('HubController — connect/error surface (A7c seam)', () => {
  it('passes provider content events straight through to the host', async () => {
    const h = harness()
    await warmed(h)
    h.getSession().events.onAssistantText?.('hello', false, null)
    h.getSession().events.onTurnDone?.(null)
    expect(h.events.onAssistantText).toHaveBeenCalledWith('hello', false, null)
    expect(h.events.onTurnDone).toHaveBeenCalledWith(null)
  })

  it('surfaces a session error with aliveForMs and drops the handle so ensureWarm rebuilds', async () => {
    const h = harness()
    await warmed(h)
    h.now.value = 6_000 // connected at 1_000 → alive 5_000 ms

    h.getSession().fail('socket closed (1006)', true)
    expect(h.events.onError).toHaveBeenCalledWith({
      reason: 'socket closed (1006)',
      retryable: true,
      aliveForMs: 5_000
    })
    expect(h.controller.isWarm()).toBe(false)
    expect(h.controller.isAvailable()).toBe(false)

    // A fresh warm mints again and builds a new session.
    const p = h.controller.ensureWarm()
    await tick()
    h.getSession().connect()
    await p
    expect(h.mintToken).toHaveBeenCalledTimes(2)
    expect(h.createSession).toHaveBeenCalledTimes(2)
  })
})

describe('HubController — A7c reconnect policy (B: strike-bounded re-warm)', () => {
  // Fail the in-flight (connecting, never-connected) warm attempt and let the reject
  // settle so the controller's `warming` clears before the next re-warm fires.
  async function failBeforeConnect(h: Harness, closeCode = 1008): Promise<void> {
    h.getSession().fail(`websocket closed (${closeCode})`, true, closeCode)
    await tick()
  }

  it('a genuine failure arms a backoff and re-warms itself so the NEXT press is warm', async () => {
    const h = harness()
    await warmed(h) // connected at now=1000
    h.now.value = 5_000 // alive 4 s (< idle window) → a real failure, not an idle close

    h.getSession().fail('websocket closed (1011)', true, 1011)
    expect(h.controller.isAvailable()).toBe(false)
    expect(h.pendingReconnect()).toBe(true)

    // The backoff elapses → the controller re-warms itself with NO user press.
    h.fireReconnect()
    await tick()
    h.getSession().connect()
    expect(h.controller.isWarm()).toBe(true)
    expect(h.mintToken).toHaveBeenCalledTimes(2)
  })

  it('caps re-warm attempts at the strike budget when the socket keeps failing before it connects', async () => {
    const h = harness()
    const p = h.controller.ensureWarm()
    p.catch(() => {}) // each attempt rejects when it fails before connecting
    await tick() // first session connecting

    let reWarms = 0
    for (let i = 0; i < 12; i++) {
      await failBeforeConnect(h) // never connected → aliveForMs 0 → a policy_fast strike
      if (!h.pendingReconnect()) break
      h.fireReconnect()
      await tick()
      reWarms++
    }
    // MAX_RECONNECT_STRIKES = 5 re-warms allowed, then a dead endpoint stops being hammered.
    expect(reWarms).toBe(5)
    expect(h.pendingReconnect()).toBe(false)
  })

  it('a completed turn resets the strike budget (a bare connect does NOT)', async () => {
    const h = harness()
    const p = h.controller.ensureWarm()
    p.catch(() => {})
    await tick()

    // Bank 4 strikes via fail-before-connect.
    for (let i = 0; i < 4; i++) {
      await failBeforeConnect(h)
      h.fireReconnect()
      await tick()
    }
    // Connecting alone must NOT refresh the budget; a completed turn must.
    h.getSession().connect()
    h.getSession().events.onTurnDone?.(null)

    // Budget refreshed → a fresh failure run gets the full 5 re-warms again (would be
    // only 1 if the 4 banked strikes had survived).
    let reWarms = 0
    for (let i = 0; i < 12; i++) {
      await failBeforeConnect(h)
      if (!h.pendingReconnect()) break
      h.fireReconnect()
      await tick()
      reWarms++
    }
    expect(reWarms).toBe(5)
  })

  it('a socket that survives past the idle window refreshes the strike budget', async () => {
    const h = harness()
    const p = h.controller.ensureWarm()
    p.catch(() => {})
    await tick()
    // Bank 4 strikes.
    for (let i = 0; i < 4; i++) {
      await failBeforeConnect(h)
      h.fireReconnect()
      await tick()
    }
    // This attempt CONNECTS and survives past the idle window before failing → the
    // long-lived socket proved the endpoint works, so the budget resets (then spends 1).
    h.getSession().connect() // connectedAt = now (1000)
    h.now.value = 1_000 + HUB_IDLE_TEARDOWN_THRESHOLD_MS + 1
    h.getSession().fail('websocket closed (1011)', true, 1011)
    if (h.pendingReconnect()) {
      h.fireReconnect()
      await tick()
    }
    // 4 more re-warms remain (a full budget of 5 minus the 1 just spent). Without the
    // survival reset the 4 banked strikes would have capped this immediately (0 more).
    let reWarms = 0
    for (let i = 0; i < 12; i++) {
      await failBeforeConnect(h)
      if (!h.pendingReconnect()) break
      h.fireReconnect()
      await tick()
      reWarms++
    }
    expect(reWarms).toBe(4)
  })
})
