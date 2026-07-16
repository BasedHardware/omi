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
import { MintError } from '../tokenMint'
import { HubController, type HubControllerEvents } from './hubController'
import { HUB_IDLE_TEARDOWN_THRESHOLD_MS } from './hubClose'

/** A provider-scoped mint failure (unconfigured / quota / auth / outage) — the class
 *  that warrants trying the OTHER realtime provider. */
const providerDownMint = (message = 'provider down'): MintError =>
  new MintError({ message, retryable: true, tryOtherProvider: true })
/** A session-wide mint failure (401/402/403) — must NOT trigger cross-provider failover. */
const sessionWideMint = (message = 'sign in'): MintError =>
  new MintError({ message, retryable: false, tryOtherProvider: false })

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

function harness(opts?: {
  provider?: VoiceProvider
  instructions?: string
  mintToken?: (provider: VoiceProvider) => Promise<string>
  fetchTools?: () => Promise<
    { name: string; description: string; parameters: Record<string, unknown> }[]
  >
}): Harness {
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
  const mintToken = vi.fn(opts?.mintToken ?? (async (_p: VoiceProvider) => 'ek_token'))
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
    fetchTools: opts?.fetchTools,
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

/** Fail the in-flight (connecting, never-connected) warm attempt and let the reject
 *  settle so the controller's `warming` clears before the next re-warm fires. */
async function failBeforeConnect(h: Harness, closeCode = 1008): Promise<void> {
  h.getSession().fail(`websocket closed (${closeCode})`, true, closeCode)
  await tick()
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

describe('HubController — requestSessionRefresh (A7c wake / zombie-session refresh)', () => {
  it('idle + warm: drops the possibly-dead socket and re-warms a fresh session', async () => {
    const h = harness()
    await warmed(h)
    const stale = h.getSession()
    expect(stale.isWarm()).toBe(true)

    h.controller.requestSessionRefresh('system_wake')

    // The zombie socket is dropped immediately (teardown), not reused as "already warm".
    expect(stale.toreDown).toBe(1)
    expect(h.controller.isWarm()).toBe(false)

    // A fresh session is minted + connected so the NEXT press lands on a warm socket.
    await tick()
    const fresh = h.getSession()
    expect(fresh).not.toBe(stale)
    fresh.connect()
    expect(h.mintToken).toHaveBeenCalledTimes(2)
    expect(h.createSession).toHaveBeenCalledTimes(2)
    expect(h.controller.isWarm()).toBe(true)
  })

  it('mid-turn: defers (never tears down a live turn) and re-warms once the turn terminates', async () => {
    const h = harness()
    await warmed(h)
    const stale = h.getSession()
    h.controller.beginTurn(t1) // already warm → an ACTIVE turn is in flight

    h.controller.requestSessionRefresh('system_wake')

    // Deferred: the live turn's socket is untouched — no teardown, no re-mint.
    expect(stale.toreDown).toBe(0)
    expect(h.controller.isWarm()).toBe(true)
    expect(h.mintToken).toHaveBeenCalledTimes(1)

    // The turn ends → the deferred refresh fires: stale socket dropped, fresh warm.
    h.controller.voiceTurnDidTerminate(t1)
    expect(stale.toreDown).toBe(1)
    await tick()
    h.getSession().connect()
    expect(h.mintToken).toHaveBeenCalledTimes(2)
    expect(h.createSession).toHaveBeenCalledTimes(2)
    expect(h.controller.isWarm()).toBe(true)
  })

  it('no warm session: is a no-op — wake never force-warms a disabled / signed-out hub', () => {
    const h = harness()
    // Never warmed (kill-switch off / signed out) → no session to refresh.
    h.controller.requestSessionRefresh('system_wake')
    expect(h.mintToken).not.toHaveBeenCalled()
    expect(h.createSession).not.toHaveBeenCalled()
    expect(h.controller.isWarm()).toBe(false)
    expect(h.controller.isAvailable()).toBe(false)
  })

  it('mid-connect: is a no-op — an in-flight warm is already building a fresh socket', async () => {
    const h = harness()
    const p = h.controller.ensureWarm() // warm in flight (session created, still connecting)
    await tick()
    const connecting = h.getSession()

    h.controller.requestSessionRefresh('system_wake')

    // The in-flight warm is left to finish — not torn down, no second mint that would
    // race it.
    expect(connecting.toreDown).toBe(0)
    expect(h.mintToken).toHaveBeenCalledTimes(1)

    connecting.connect()
    await p
    expect(h.controller.isWarm()).toBe(true)
    expect(h.createSession).toHaveBeenCalledTimes(1)
  })
})

describe('HubController — ensureWarm teardown race (M1: cancelable warm)', () => {
  it('a teardownSession while the token is minting discards the warm — no orphaned session is installed', async () => {
    let resolveMint: (t: string) => void = () => {}
    const mintToken = vi.fn(
      (_p: VoiceProvider) => new Promise<string>((res) => (resolveMint = res))
    )
    const h = harness({ mintToken })

    const p = h.controller.ensureWarm()
    p.catch(() => {}) // the aborted warm rejects — swallow so it is not an unhandled rejection
    await tick() // parked on the mint await, before any session is constructed

    // The hub is explicitly dropped (kill-switch off / sign-out) mid-mint — exactly the
    // wake-deferred-refresh path where teardownSession runs while this warm is still
    // minting and this.session is null (so teardown cannot cancel the not-yet-built one).
    h.controller.teardownSession()

    resolveMint('ek_token') // the in-flight mint finally resolves…
    await tick()

    // …and the warm bails BEFORE constructing a session: no orphaned socket to re-warm.
    expect(h.createSession).not.toHaveBeenCalled()
    expect(h.controller.isAvailable()).toBe(false)
    expect(h.controller.isWarm()).toBe(false)
    await expect(p).rejects.toThrow('hub warm aborted by teardown')
  })

  it('a teardownSession after the warm resolves but before it installs discards the session (no leak)', async () => {
    const h = harness()
    const p = h.controller.ensureWarm()
    p.catch(() => {})
    await tick() // session constructed, connecting
    const s = h.getSession()

    // The socket connects (markReady → onConnected → warm resolves), then — before the
    // ensureWarm continuation runs — the hub is explicitly dropped. warmReject is already
    // cleared, so the session is torn down but NOT rejected; the generation guard is what
    // stops this resolved-then-dropped session from being installed as the live hub.
    s.connect()
    h.controller.teardownSession()
    await tick() // the ensureWarm continuation runs and aborts on the moved generation

    expect(h.controller.isAvailable()).toBe(false)
    expect(h.controller.isWarm()).toBe(false)
    expect(s.toreDown).toBeGreaterThanOrEqual(1) // the created socket was closed, not leaked
    await expect(p).rejects.toThrow('hub warm aborted by teardown')
  })

  it('overlapping warms WITHOUT a teardown still coalesce to a single warm (no regression)', async () => {
    const h = harness()
    const a = h.controller.ensureWarm()
    const b = h.controller.ensureWarm() // straddles the same in-flight warm
    await tick()
    h.getSession().connect()

    const [sa, sb] = await Promise.all([a, b])
    expect(sa).toBe(SID)
    expect(sb).toBe(SID)
    // One mint, one session — the generation guard did not fracture the coalescing.
    expect(h.mintToken).toHaveBeenCalledTimes(1)
    expect(h.createSession).toHaveBeenCalledTimes(1)
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

  it('surfaces the silent post-commit death: a fallback event fires exactly when the re-warm budget runs out', async () => {
    const h = harness()
    await warmed(h) // socket connected at now=1000

    // A completed turn proves this is POST-COMMIT (and resets the strike budget to 0),
    // then the warm socket dies and the re-warm keeps rebuilding and losing FAST (each
    // attempt alive < the idle window), so nothing resets the budget — the exact repeated
    // post-commit provider death that used to drop every later turn to a silent cascade.
    h.getSession().events.onTurnDone?.(null)
    expect(trackEvent).not.toHaveBeenCalled()

    // The first death is of the connected socket; each subsequent re-warm fails fast.
    let reWarms = 0
    h.getSession().fail('websocket closed (1006)', true, 1006) // aliveForMs 0 → a fast strike
    for (let i = 0; i < 12; i++) {
      if (!h.pendingReconnect()) break // budget exhausted → re-warm stopped
      h.fireReconnect()
      await tick() // next session connecting
      reWarms++
      await failBeforeConnect(h, 1006) // …and it dies before connecting → another strike
    }

    // 5 re-warms, then the circuit trips. The death is no longer silent: exactly one
    // shared fallback event (closed enums, no new counter), distinct from the warm-wait
    // `degraded` handoff and the host's per-turn `exhausted` terminal.
    expect(reWarms).toBe(5)
    expect(h.pendingReconnect()).toBe(false)
    expect(trackEvent).toHaveBeenCalledExactlyOnceWith('fallback_triggered', {
      component: 'ptt_cascade',
      from: 'hub',
      to: 'none',
      reason: 'circuit_open',
      outcome: 'exhausted'
    })
  })

  it('does NOT emit a fallback event while the hub self-heals below the strike budget', async () => {
    const h = harness()
    await warmed(h)
    h.now.value = 5_000 // alive 4 s (< idle window) → a real, strike-consuming failure

    // A single post-commit death that re-warms successfully is silent UX healing — it
    // must NOT emit the `exhausted` fallback (that is reserved for a dead endpoint).
    h.getSession().fail('websocket closed (1011)', true, 1011)
    h.fireReconnect()
    await tick()
    h.getSession().connect()

    expect(h.controller.isWarm()).toBe(true)
    expect(trackEvent).not.toHaveBeenCalled()
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

describe('HubController — A7c reconnect policy (C: idle-teardown survival)', () => {
  it('an expected idle-close proactively re-warms so isAvailable() is true BEFORE the next press', async () => {
    const h = harness()
    await warmed(h) // connected at now=1000
    h.now.value = 1_000 + HUB_IDLE_TEARDOWN_THRESHOLD_MS + 1 // long-lived, no active turn
    h.getSession().fail('websocket closed (1008)', true, 1008) // → expected_idle_teardown

    // The socket is gone, but the controller has armed a proactive re-warm (no press).
    expect(h.controller.isAvailable()).toBe(false)
    expect(h.pendingReconnect()).toBe(true)

    h.fireReconnect()
    await tick()
    // A session object now exists again BEFORE any press → selectPttRoute will pick the
    // warm lane (hubWarmWait), not a cold cascade.
    expect(h.controller.isAvailable()).toBe(true)
    h.getSession().connect()
    expect(h.controller.isWarm()).toBe(true)
    expect(h.mintToken).toHaveBeenCalledTimes(2)
  })

  it('an idle teardown re-warms WITHOUT spending a strike (the failure budget stays full)', async () => {
    const h = harness()
    await warmed(h) // connected at now=1000
    // aliveFor EXACTLY the threshold: an idle teardown (classify uses >=), but the
    // >60 s strike RESET (uses strict >) does NOT fire — so this isolates "idle spends
    // no strike" from "a long-lived socket resets the budget".
    h.now.value = 1_000 + HUB_IDLE_TEARDOWN_THRESHOLD_MS
    h.getSession().fail('websocket closed (1008)', true, 1008)
    expect(h.pendingReconnect()).toBe(true)
    h.fireReconnect()
    await tick() // session connecting (never connected → no reset)

    // The idle close spent no strike, so the full failure budget of 5 remains — 5 fast
    // failures each still re-warm (would be only 4 if the idle close had taken a strike).
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
})

describe('HubController — A7c cross-provider failover (D: mint-based)', () => {
  /** A mint that rejects for `openai` (provider-scoped) but succeeds for `gemini`. */
  const openaiDownMint = (): ((p: VoiceProvider) => Promise<string>) =>
    vi.fn(async (p: VoiceProvider) => {
      if (p === 'openai') throw providerDownMint('openai down')
      return 'ek_gemini'
    })

  it('fails over to the alternate provider when the primary mint fails provider-scoped', async () => {
    const h = harness({ provider: 'openai', mintToken: openaiDownMint() })
    const p = h.controller.ensureWarm()
    await tick() // primary mint rejects → failover → alternate mint resolves → session created
    h.getSession().connect()
    const sid = await p

    expect(sid).toBe(SID)
    // The effective provider flipped: primary minted first, then the alternate warmed.
    expect(h.mintToken).toHaveBeenNthCalledWith(1, 'openai')
    expect(h.mintToken).toHaveBeenNthCalledWith(2, 'gemini')
    expect(h.mintToken).toHaveBeenCalledTimes(2)
    expect(h.createSession).toHaveBeenCalledTimes(1)
    expect(h.createSession.mock.calls[0][0].provider).toBe('gemini')
    expect(h.controller.isWarm()).toBe(true)
  })

  it('records degraded on the switch and recovered when the alternate connects', async () => {
    const h = harness({ provider: 'openai', mintToken: openaiDownMint() })
    const p = h.controller.ensureWarm()
    await tick()
    // No telemetry until the alternate actually connects beyond the degraded switch.
    expect(trackEvent).toHaveBeenCalledExactlyOnceWith('fallback_triggered', {
      component: 'realtime_hub',
      from: 'openai',
      to: 'gemini',
      reason: 'provider_unavailable',
      outcome: 'degraded'
    })
    h.getSession().connect()
    await p

    expect(trackEvent).toHaveBeenCalledTimes(2)
    expect(trackEvent).toHaveBeenLastCalledWith('fallback_triggered', {
      component: 'realtime_hub',
      from: 'openai',
      to: 'gemini',
      reason: 'provider_unavailable',
      outcome: 'recovered'
    })
  })

  it('surfaces the error when BOTH providers fail to mint (once-per-chain, no loop)', async () => {
    const bothDown = vi.fn(async (_p: VoiceProvider) => {
      throw providerDownMint('all providers down')
    })
    const h = harness({ provider: 'openai', mintToken: bothDown })

    await expect(h.controller.ensureWarm()).rejects.toThrow('all providers down')
    // Exactly two mint attempts — the primary, then the ONE alternate — never a loop.
    expect(bothDown).toHaveBeenCalledTimes(2)
    expect(bothDown).toHaveBeenNthCalledWith(1, 'openai')
    expect(bothDown).toHaveBeenNthCalledWith(2, 'gemini')
    // degraded on the switch, then exhausted when the alternate is down too.
    expect(trackEvent).toHaveBeenNthCalledWith(1, 'fallback_triggered', {
      component: 'realtime_hub',
      from: 'openai',
      to: 'gemini',
      reason: 'provider_unavailable',
      outcome: 'degraded'
    })
    expect(trackEvent).toHaveBeenNthCalledWith(2, 'fallback_triggered', {
      component: 'realtime_hub',
      from: 'gemini',
      to: 'none',
      reason: 'provider_unavailable',
      outcome: 'exhausted'
    })
    expect(trackEvent).toHaveBeenCalledTimes(2)
  })

  it('does NOT fail over for a session-wide mint failure (401/402/403) — surfaces unchanged', async () => {
    const sessionWide = vi.fn(async (_p: VoiceProvider) => {
      throw sessionWideMint('sign in to use voice')
    })
    const h = harness({ provider: 'openai', mintToken: sessionWide })

    await expect(h.controller.ensureWarm()).rejects.toThrow('sign in to use voice')
    // No alternate attempt, no fallback telemetry — this is the cascade drop, unchanged.
    expect(sessionWide).toHaveBeenCalledExactlyOnceWith('openai')
    expect(trackEvent).not.toHaveBeenCalled()
  })

  it('resets the failover on a long-lived socket close so the next chain starts on the primary', async () => {
    const mint = openaiDownMint()
    const h = harness({ provider: 'openai', mintToken: mint })
    // Warm → primary down → fail over to the alternate → connect.
    const p = h.controller.ensureWarm()
    await tick()
    h.getSession().connect() // connectedAt = now (1000), provider = gemini
    await p
    expect(h.mintToken).toHaveBeenLastCalledWith('gemini')

    // The primary recovers; the alternate socket survives past the idle window, then
    // closes → the proven-good signal returns us to the primary on the next warm.
    vi.mocked(mint).mockImplementation(async (_p: VoiceProvider) => 'ek_ok')
    h.now.value = 1_000 + HUB_IDLE_TEARDOWN_THRESHOLD_MS + 1
    h.getSession().fail('websocket closed (1008)', true, 1008)
    expect(h.pendingReconnect()).toBe(true)

    // The proactive re-warm now mints the PRIMARY (openai) again, not the alternate.
    h.fireReconnect()
    await tick()
    expect(h.mintToken).toHaveBeenLastCalledWith('openai')
  })
})

describe('HubController — tool loop (PR-C)', () => {
  it('passes the fetched catalog into the session it builds', async () => {
    const tools = [
      {
        name: 'list_agent_sessions',
        description: 'list',
        parameters: { type: 'object', properties: {} }
      }
    ]
    const h = harness({ fetchTools: () => Promise.resolve(tools) })
    await warmed(h)
    const spec = h.createSession.mock.calls[0][0] as { tools?: unknown[] }
    expect(spec.tools).toEqual(tools)
  })

  it('warms tool-less when no fetchTools seam is wired', async () => {
    const h = harness()
    await warmed(h)
    const spec = h.createSession.mock.calls[0][0] as { tools?: unknown[] }
    expect(spec.tools).toEqual([])
  })

  it('warms tool-less (does not fail the session) when the catalog fetch rejects', async () => {
    const h = harness({ fetchTools: () => Promise.reject(new Error('ipc down')) })
    await warmed(h)
    expect(h.controller.isWarm()).toBe(true)
    const spec = h.createSession.mock.calls[0][0] as { tools?: unknown[] }
    expect(spec.tools).toEqual([])
  })

  it('relays a tool result to the warm session keyed by callId', async () => {
    const h = harness()
    await warmed(h)
    h.controller.sendToolResult('call-1', 'list_agent_sessions', '{"ok":true}')
    expect(h.getSession().toolResults).toEqual([{ callId: 'call-1', output: '{"ok":true}' }])
  })

  it('sendToolResult is a no-op with no warm session (torn-down / barged-in turn)', () => {
    const h = harness()
    // Never warmed → no session; must not throw.
    expect(() => h.controller.sendToolResult('c', 'n', 'o')).not.toThrow()
  })
})
