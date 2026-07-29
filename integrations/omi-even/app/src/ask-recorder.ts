/** One dictated question: microphone on, PCM to the bridge, microphone off.
 *
 *  Split out of `main.ts` because this is the part with the teeth in it. The
 *  microphone is real hardware on the user's face: every path out of listening
 *  — tap, cancel, cap, error, bridge loss, page unload — has to turn it off,
 *  and every binary frame has to sit strictly between `ask_start` and
 *  `ask_stop` or the bridge files it as continuous-capture audio instead.
 *
 *  Nothing here touches the SDK or the display directly, so the whole lifecycle
 *  is exercised in `scripts/unit-test.mjs` with fakes.
 */
import { peakLevel, toPcmBytes } from './audio.ts'
import { ASK_TICK_MS, askMaxMs } from './config.ts'
import type { OutboundMessage } from './protocol.ts'

/** Why a listening session ended. Only `tap` and `cap` want an answer back. */
export type StopReason = 'tap' | 'cap' | 'cancel' | 'teardown'

export type StartFailure = 'offline' | 'mic'

export type AskDeps = {
  /** Send one JSON control frame. False means the socket is not open. */
  sendJson: (message: OutboundMessage) => boolean
  /** Send one binary PCM frame. False means dropped (closed or backed up). */
  sendBinary: (pcm: Uint8Array) => boolean
  /** Turn the glasses microphone on or off. False means the call failed. */
  setMic: (on: boolean) => Promise<boolean>
  /** Redraw request: the meter, the timer, or the phase changed. */
  onUpdate: () => void
  /** The hard cap expired. The caller runs its normal stop path from here so
   *  an auto-stop and a tap-stop cannot drift apart. */
  onCap: () => void
  /** Overrides, for tests. */
  maxMs?: number
  tickMs?: number
  now?: () => number
}

export class AskRecorder {
  private readonly deps: AskDeps
  private readonly maxMs: number
  private readonly tickMs: number
  private readonly now: () => number

  private listening = false
  private startedAt = 0
  private capTimer: ReturnType<typeof setTimeout> | null = null
  private ticker: ReturnType<typeof setInterval> | null = null

  /** Peak of the frames seen since the last tick, so the meter tracks the
   *  voice rather than sitting at whatever the loudest sample ever was. */
  private windowPeak = 0
  private displayLevel = 0

  bytesSent = 0
  framesSent = 0
  framesDropped = 0
  /** Frames that arrived while not listening. Expected — the microphone keeps
   *  running when Capture is on — but a nonzero count outside that case means
   *  the bracket leaked. */
  framesIgnored = 0

  constructor(deps: AskDeps) {
    this.deps = deps
    this.maxMs = deps.maxMs ?? askMaxMs()
    this.tickMs = deps.tickMs ?? ASK_TICK_MS
    this.now = deps.now ?? (() => Date.now())
  }

  isListening(): boolean {
    return this.listening
  }

  elapsedMs(): number {
    return this.listening ? this.now() - this.startedAt : 0
  }

  remainingMs(): number {
    return Math.max(0, this.maxMs - this.elapsedMs())
  }

  capMs(): number {
    return this.maxMs
  }

  level(): number {
    return this.displayLevel
  }

  /**
   * Open the bracket, then the microphone. That order matters: a microphone
   * with nowhere to send is the one state that costs the user battery for
   * nothing, so the socket is proven first and the mic is only opened once
   * `ask_start` is actually on the wire.
   */
  async start(): Promise<{ ok: true } | { ok: false; reason: StartFailure }> {
    if (this.listening) return { ok: true }

    this.bytesSent = 0
    this.framesSent = 0
    this.framesDropped = 0
    this.windowPeak = 0
    this.displayLevel = 0

    if (!this.deps.sendJson({ type: 'ask_start' })) {
      console.warn('[app] ask start aborted: bridge offline')
      return { ok: false, reason: 'offline' }
    }

    if (!(await this.deps.setMic(true))) {
      // Close the bracket we just opened, or the bridge stays in ask mode and
      // files the next continuous-capture frame as part of a question.
      this.deps.sendJson({ type: 'ask_stop' })
      return { ok: false, reason: 'mic' }
    }

    this.listening = true
    this.startedAt = this.now()
    console.log(`[app] listening (cap ${Math.round(this.maxMs / 1000)}s)`)

    this.capTimer = setTimeout(() => {
      this.capTimer = null
      console.log('[app] listening cap reached')
      this.deps.onCap()
    }, this.maxMs)

    this.ticker = setInterval(() => this.tick(), this.tickMs)
    return { ok: true }
  }

  /**
   * Close the bracket. Always sends `ask_stop`, even on a cancel: the bridge
   * has a buffer open and only `ask_stop` releases it. The caller discards the
   * response instead.
   *
   * Returns whether `ask_stop` actually reached the socket — false means the
   * bridge never heard the question, so no answer is owed and none is coming.
   */
  async stop(reason: StopReason): Promise<boolean> {
    if (!this.listening) return false
    // Cleared first so frames still in flight from the last 100ms are dropped
    // rather than escaping past `ask_stop`.
    this.listening = false
    this.clearTimers()

    const seconds = ((this.now() - this.startedAt) / 1000).toFixed(1)
    // The microphone comes first: if `ask_stop` fails to send, the hardware is
    // still off, which is the failure that actually costs the user something.
    const micOff = await this.deps.setMic(false)
    if (!micOff) console.error('[app] microphone may still be on after stop')
    const asked = this.deps.sendJson({ type: 'ask_stop' })
    console.log(
      `[app] stopped listening (${reason}, ${seconds}s, ${this.framesSent} frame(s), ${this.bytesSent} bytes` +
        `${this.framesDropped > 0 ? `, ${this.framesDropped} dropped` : ''})`,
    )
    return asked
  }

  /**
   * One `audioEvent` payload. Called for every frame the host delivers,
   * including while Capture holds the microphone open with no question being
   * asked — those are counted and dropped, never sent, because an unbracketed
   * binary frame means "continuous capture" to the bridge.
   */
  feed(raw: unknown): void {
    if (!this.listening) {
      this.framesIgnored++
      return
    }
    const pcm = toPcmBytes(raw)
    if (!pcm) {
      this.framesDropped++
      return
    }
    const peak = peakLevel(pcm)
    if (peak > this.windowPeak) this.windowPeak = peak

    if (this.deps.sendBinary(pcm)) {
      this.bytesSent += pcm.length
      this.framesSent++
    } else {
      this.framesDropped++
    }
  }

  /** Last-ditch stop for unload/teardown, where nothing can be awaited. */
  teardown(): void {
    if (!this.listening) return
    this.listening = false
    this.clearTimers()
    void this.deps.setMic(false)
    this.deps.sendJson({ type: 'ask_stop' })
    console.log('[app] listening torn down')
  }

  private clearTimers(): void {
    if (this.capTimer !== null) clearTimeout(this.capTimer)
    if (this.ticker !== null) clearInterval(this.ticker)
    this.capTimer = null
    this.ticker = null
  }

  private tick(): void {
    // Decay rather than snap to zero, so a gap between words does not read as
    // "the microphone died".
    this.displayLevel = Math.max(this.windowPeak, this.displayLevel * 0.6)
    this.windowPeak = 0
    // Two lines a second while listening, and never otherwise: enough to prove
    // from a log that audio really moved, without drowning the console.
    console.log(
      `[app] audio ${this.framesSent} frame(s), ${this.bytesSent} bytes, level=${this.displayLevel.toFixed(2)}`,
    )
    this.deps.onUpdate()
  }
}
