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
// The sampler is TRUSTED ONLY AFTER IT HAS OBSERVED THE KEY DOWN in this
// gesture. GetAsyncKeyState can be blind to a physically-held key (it returns 0
// for a non-elevated caller while an elevated/UIPI-protected window has the
// foreground, and after some focus/desktop transitions) while RegisterHotKey
// keeps firing system-wide. The shipped bug: a single blind UP sample ended a
// real hold as 'tap' 30ms in, and every subsequent auto-repeat fire started a
// new tap gesture — the field logs' bursts of down/up `kind=tap` pairs that
// silently discarded deliberate holds. Now the repeat-gap grouping runs as the
// authority until the poll actually sees the key down (the auto-repeat fires
// ARE proof the key is held), and once sighted, a release needs
// RELEASE_CONFIRM_SAMPLES consecutive UP reads so one stray sample can't end a
// hold.
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
  /** The absolute hold cap tripped — the sampler kept reading the key DOWN past
   *  maxHoldMs, so the physical key-up was almost certainly missed (GetAsyncKeyState
   *  can go stale-down after a focus/session transition). Fired once, immediately
   *  before onEnd, so the caller can log it distinctly. Recovery only — a real hold
   *  is already useless past the ~4.5-min buffer cap. */
  onCapExceeded?: () => void
}

export type SummonGestureOptions = {
  /** Sample "is the chord's key physically down right now" — null if unavailable. */
  sampleKeyDown: (() => boolean) | null
  holdThresholdMs?: number
  pollMs?: number
  repeatGapMs?: number
  maxHoldMs?: number
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

/** Tap/hold boundary — macOS parity: PushToTalkManager.tapToLockMaxHoldDuration
 *  (0.22s) is the release-time boundary between a tap and a genuine hold on the
 *  proven implementation. Was 350ms, which left a 220–350ms band Mac records
 *  but Windows silently dropped. */
export const HOLD_THRESHOLD_MS = 220
export const POLL_MS = 30
/** Must exceed the slowest Windows keyboard initial repeat delay (~1s). */
export const REPEAT_GAP_MS = 1200
/** Consecutive UP poll samples required (after the key has been seen down)
 *  before the gesture ends — one transiently-blind GetAsyncKeyState read must
 *  not end a real hold. Costs one poll interval (~30ms) of release latency. */
export const RELEASE_CONFIRM_SAMPLES = 2
/** Absolute sampler-mode hold cap: force-end a gesture the poll still reads as
 *  DOWN after this long. Matches the renderer's ~4.5-min PCM buffer cap
 *  (MAX_BUFFER_BYTES) with margin — audio past that can't be transcribed, so
 *  bounding the hold here can NEVER cost useful speech; it only rescues a hold
 *  whose key-up edge the poll missed (the stuck-recording-visualizer failure
 *  class). Without it, `machine.ts` WATCHDOG no-ops while `holding`, so a missed
 *  edge sticks the orb forever. */
export const MAX_HOLD_MS = 5 * 60 * 1000

export class SummonGesture {
  private active = false
  private startAt = 0
  private lastFireAt = 0
  private holdFired = false
  /** The poll has read the key DOWN at least once this gesture — only then is
   *  the sampler trusted to report the release (see header comment). */
  private keyObservedDown = false
  /** Consecutive UP samples seen since the last DOWN sample. */
  private upSamples = 0
  /** Clock time of the first UP sample of the current confirm run — the
   *  accurate release moment (end() fires RELEASE_CONFIRM_SAMPLES polls later). */
  private upFirstAt = 0
  private pollTimer: unknown = null
  private gapTimer: unknown = null

  private readonly sample: (() => boolean) | null
  private readonly holdThresholdMs: number
  private readonly pollMs: number
  private readonly repeatGapMs: number
  private readonly maxHoldMs: number
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
    this.maxHoldMs = opts.maxHoldMs ?? MAX_HOLD_MS
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
      // Auto-repeat inside the gesture. While the gap timer is the authority
      // (no sampler, or a sampler that hasn't yet observed the key down) each
      // fire extends the deadline — the repeats are the proof the key is held.
      this.lastFireAt = this.now()
      if (!this.sample || !this.keyObservedDown) this.armGapTimer()
      return
    }
    this.active = true
    this.holdFired = false
    this.keyObservedDown = false
    this.upSamples = 0
    this.upFirstAt = 0
    this.startAt = this.lastFireAt = this.now()
    this.cb.onStart()
    if (this.sample) this.armPoll()
    // The gap timer arms in BOTH modes: without a sampler it is the only end
    // mechanism; with one it is the blind-sampler safety net, disarmed the
    // moment the poll actually observes the key down.
    this.armGapTimer()
  }

  /** Tear down (app quit / rebind). Ends a live gesture as its current kind. */
  dispose(): void {
    this.clearTimers()
    if (this.active) this.end()
  }

  /** End an in-flight gesture NOW, as its current kind, because the physical
   *  key-up will never be observed — the session is locking or the machine is
   *  suspending (GetAsyncKeyState freezes across those transitions, so the poll
   *  would otherwise read the key stuck-down). onEnd fires so the hold is
   *  finalized/released rather than stranded. No-op when idle; the object stays
   *  reusable for the next press. */
  endIfActive(): void {
    if (this.active) this.end()
  }

  private clearTimers(): void {
    if (this.pollTimer !== null) {
      this.clearTimer(this.pollTimer)
      this.pollTimer = null
    }
    this.clearGapTimer()
  }

  private clearGapTimer(): void {
    if (this.gapTimer !== null) {
      this.clearTimer(this.gapTimer)
      this.gapTimer = null
    }
  }

  private end(): void {
    // Release time: a sighted sampler ends at the first UP sample of the
    // confirm run (accurate to one poll). Blind/gap endings happen a full
    // repeatGapMs after the key was released, so measure to the last fire.
    const releaseAt =
      this.sample && this.keyObservedDown
        ? this.upSamples > 0
          ? this.upFirstAt
          : this.now()
        : this.lastFireAt
    const duration = releaseAt - this.startAt
    const kind: GestureKind = this.holdFired || duration >= this.holdThresholdMs ? 'hold' : 'tap'
    if (this.sample && !this.keyObservedDown) {
      // Always-on field trace (see window.ts pttTrace): the sampler existed but
      // never saw the key down this gesture — GetAsyncKeyState was blind (e.g.
      // elevated foreground window) and the repeat-gap grouping classified it.
      console.log(
        `[ptt-diag] gesture ended BLIND (sampler never read key down; repeat-gap classified ${kind})`
      )
    }
    this.active = false
    this.clearTimers()
    this.cb.onEnd(kind)
  }

  private armPoll(): void {
    this.pollTimer = this.setTimer(() => {
      this.pollTimer = null
      if (!this.active) return
      // Absolute cap, checked regardless of what the sampler reads: a gesture
      // (sighted OR blind-but-repeat-extended) must never outlive maxHoldMs.
      if (this.now() - this.startAt >= this.maxHoldMs) {
        this.cb.onCapExceeded?.()
        this.end()
        return
      }
      if (this.sample!()) {
        if (!this.keyObservedDown) {
          // First confirmed DOWN — the sampler is now the authority; the
          // repeat-gap safety net stands down.
          this.keyObservedDown = true
          this.clearGapTimer()
        }
        this.upSamples = 0
        if (!this.holdFired && this.now() - this.startAt >= this.holdThresholdMs) {
          this.holdFired = true
          this.cb.onHoldStart?.()
        }
        this.armPoll()
      } else if (!this.keyObservedDown) {
        // Blind so far: an UP read proves nothing — GetAsyncKeyState can be
        // blocked while the key is physically held, and the auto-repeat fires
        // arriving via fire() are the ground truth. The gap timer owns the end;
        // keep polling in case sight returns.
        this.armPoll()
      } else {
        // Sighted release candidate — require consecutive confirms so one
        // stray blind sample can't end a real hold as a tap.
        if (this.upSamples === 0) this.upFirstAt = this.now()
        this.upSamples += 1
        if (this.upSamples >= RELEASE_CONFIRM_SAMPLES) this.end()
        else this.armPoll()
      }
    }, this.pollMs)
  }

  private armGapTimer(): void {
    this.clearGapTimer()
    this.gapTimer = this.setTimer(() => {
      this.gapTimer = null
      if (this.active) this.end()
    }, this.repeatGapMs)
  }
}
