// Summon-gesture grouping for the bar hotkey — the fix for "the bar flaps
// open/closed while holding the hotkey", and the driver of the PTT-hold reveal
// path. Electron's globalShortcut fires its callback on every OS key
// auto-repeat and never reports key-up, so a naive toggle-per-fire flaps.
//
// This machine groups fires into ONE gesture:
//   - with a key-state sampler (Win32 GetAsyncKeyState via keyState.ts): the
//     gesture spans first fire → observed physical key-up. Repeat fires while
//     the key is down are ignored. Polling runs ONLY during a gesture (zero
//     idle cost). Ends classify as 'tap' (< holdThresholdMs) or 'hold'.
//   - without a sampler (koffi unavailable): fires closer together than
//     repeatGapMs extend the same gesture; it ends repeatGapMs after the last
//     fire and duration decides tap vs hold. (A held key emits repeats, so a
//     hold still groups; only users with key-repeat disabled degrade to taps.)
//
// Pure/deterministic: clock and timers are injected for the unit tests.

export type GestureKind = 'tap' | 'hold'

export type SummonGestureCallbacks = {
  /** First fire of a gesture — respond immediately (show the bar). */
  onStart: () => void
  /** The key has been physically held past holdThresholdMs (sampler mode only). */
  onHoldStart?: () => void
  /** Gesture over. `kind` is 'hold' iff it lasted ≥ holdThresholdMs. */
  onEnd: (kind: GestureKind) => void
}

export type SummonGestureOptions = {
  /** Sample "is the chord's key physically down right now" — null if unavailable. */
  sampleKeyDown: (() => boolean) | null
  holdThresholdMs?: number
  pollMs?: number
  repeatGapMs?: number
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export const HOLD_THRESHOLD_MS = 350
export const POLL_MS = 30
/** Must exceed the slowest Windows keyboard initial repeat delay (~1s). */
export const REPEAT_GAP_MS = 1200

export class SummonGesture {
  private active = false
  private startAt = 0
  private lastFireAt = 0
  private holdFired = false
  private timer: unknown = null

  private readonly sample: (() => boolean) | null
  private readonly holdThresholdMs: number
  private readonly pollMs: number
  private readonly repeatGapMs: number
  private readonly now: () => number
  private readonly setTimer: (fn: () => void, ms: number) => unknown
  private readonly clearTimer: (h: unknown) => void

  constructor(
    private cb: SummonGestureCallbacks,
    opts: SummonGestureOptions
  ) {
    this.sample = opts.sampleKeyDown
    this.holdThresholdMs = opts.holdThresholdMs ?? HOLD_THRESHOLD_MS
    this.pollMs = opts.pollMs ?? POLL_MS
    this.repeatGapMs = opts.repeatGapMs ?? REPEAT_GAP_MS
    this.now = opts.now ?? Date.now
    this.setTimer = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
    this.clearTimer = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  }

  get isActive(): boolean {
    return this.active
  }

  /** Wire to globalShortcut's callback. Repeat fires never re-trigger. */
  fire(): void {
    if (this.active) {
      // Auto-repeat inside the gesture. In gap mode this extends the deadline.
      this.lastFireAt = this.now()
      if (!this.sample) this.armGapTimer()
      return
    }
    this.active = true
    this.holdFired = false
    this.startAt = this.lastFireAt = this.now()
    this.cb.onStart()
    if (this.sample) this.armPoll()
    else this.armGapTimer()
  }

  /** Tear down (app quit / rebind). Ends a live gesture as its current kind. */
  dispose(): void {
    if (this.timer !== null) {
      this.clearTimer(this.timer)
      this.timer = null
    }
    if (this.active) this.end()
  }

  private end(): void {
    // Sampler mode ends AT key-up (now is accurate); gap mode ends a full
    // repeatGapMs after the key was released, so measure to the last fire.
    const duration = (this.sample ? this.now() : this.lastFireAt) - this.startAt
    const kind: GestureKind = this.holdFired || duration >= this.holdThresholdMs ? 'hold' : 'tap'
    this.active = false
    if (this.timer !== null) {
      this.clearTimer(this.timer)
      this.timer = null
    }
    this.cb.onEnd(kind)
  }

  private armPoll(): void {
    this.timer = this.setTimer(() => {
      this.timer = null
      if (!this.active) return
      if (this.sample!()) {
        if (!this.holdFired && this.now() - this.startAt >= this.holdThresholdMs) {
          this.holdFired = true
          this.cb.onHoldStart?.()
        }
        this.armPoll()
      } else {
        this.end()
      }
    }, this.pollMs)
  }

  private armGapTimer(): void {
    if (this.timer !== null) this.clearTimer(this.timer)
    this.timer = this.setTimer(() => {
      this.timer = null
      if (this.active) this.end()
    }, this.repeatGapMs)
  }
}
