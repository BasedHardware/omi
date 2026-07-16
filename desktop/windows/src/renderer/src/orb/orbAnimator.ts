// Self-throttled animation driver for the orb in the APP (the harness never
// uses this — it scrubs time directly). Owns the clock and the rAF loop:
//   idle / quiet listening → 30fps
//   active states          → 60fps (speaking / thinking / agents, genesis,
//                            morph, and while the speech blob is dissolving)
//   hidden                 → 0fps (loop fully stopped — the orb must cost nothing)
// Frame timestamps can be logged (OrbAnimator.frameLog) so the throttle states
// are assertable by the perf harness.
//
// Speech visualization: callers feed real signals — setSpeechActive(true) when
// the VAD gate opens / PTT is capturing, setAmplitude(raw) with the live level.
// The animator steps the deterministic merge + amplitude envelopes per frame,
// so the blob conglomerates on speech, waves with the (bounded) voice, and
// dissolves back to the orbiting dots when speech ends.
import {
  computeOrbFrame,
  easeInOut,
  genesisSettled,
  mergeAmount,
  spinTargetFor,
  anchorWhirlStart,
  orbitFlowFor,
  stepMergeEnvelope,
  stepAmplitudeEnvelope,
  waveMixFor,
  SPIN_EASE_TAU,
  FLOW_EASE_TAU,
  FAIL_GESTURE_MS,
  DEFAULT_ORB_PARAMS,
  type OrbParams,
  type OrbState
} from './choreography'
import {
  WAVE_MAX_SLOTS,
  slotCountForAspect,
  shapeBarLevel,
  historyPush,
  historySlots,
  stepWaveLevels
} from './waveform'
import { OrbRenderer, DEFAULT_MORPH_RECT, type OrbRect } from './orbRenderer'

/** How often (seconds) a new loudness sample scrolls into the waveform row —
 *  decoupled from the frame rate so the scroll speed is steady at 30 or 60fps. */
const WAVE_SAMPLE_SEC = 0.06

const IDLE_FPS = 30
const ACTIVE_FPS = 60
/** Morph tween length, seconds (disc ↔ rounded rect). */
const MORPH_SECONDS = 0.28

export class OrbAnimator {
  private canvas: HTMLCanvasElement
  private renderer: OrbRenderer
  /** True between a `webglcontextlost` and its `webglcontextrestored`. */
  private contextLost = false
  private params: OrbParams
  private state: OrbState = 'idle'
  private stateChangedAt = 0
  /** Effective merge captured at the last state change — the new state's ramp
   *  cross-fades from it so the blob never snaps (C6). */
  private enterMerge = 0
  /** Live orbit-speed multiplier, eased toward the current state's target, and
   *  the warped orbit clock it integrates (C9 — faster spin while busy). */
  private spinMult = 1
  private orbitTime = 0
  /** Time (animator clock) the entry-whirl's decay counts from — latched when the
   *  ring RE-FORMS (waveMix < eps), not at state entry, so the whirl lands on the
   *  visible ring after a speaking→thinking roll-up. null = primed, not yet
   *  latched (held at full overshoot). Reset on every setState. */
  private whirlStartAt: number | null = null
  /** Live orbit cadence 0..1 (step-rest ↔ continuous glide), eased toward the
   *  current state's target so the crossover is smooth (busy states glide). */
  private flow = 0
  private summonedAt: number | null = null
  /** Animator-clock time the fail tremor was stamped (null = none has played, or
   *  the last one long since settled). Held after settle — isActive() only counts
   *  it live within the FAIL_GESTURE_MS window. */
  private failedAt: number | null = null
  private morphTarget = 0
  private morph = 0
  /** Raw live level target (from the mic pipeline) and its smoothed envelope. */
  private rawAmplitude = 0
  private ampEnvelope = 0
  /** Speech-merge envelope: eases to 1 while speech is active, dissolves to 0.
   *  Doubles as the waveform crossfade (ring dots → bar visualizer). */
  private speechActive = false
  private speechMerge = 0
  /** Waveform: the canvas aspect (fixed per mount), the loudness history ring,
   *  and the eased per-slot display levels the shader renders as bars. */
  private aspect = 1
  private slotCount = slotCountForAspect(1)
  private waveHistory = new Float32Array(WAVE_MAX_SLOTS)
  private waveWrite = 0
  private wavePushAccum = 0
  private waveDisplay = new Float32Array(slotCountForAspect(1))
  private visible = true
  private raf: number | null = null
  private lastFrameAt = 0
  private epoch = performance.now() / 1000
  private lastTime = 0
  private rect: OrbRect = DEFAULT_MORPH_RECT
  /** Rolling log of rendered-frame timestamps (ms), for throttle assertions. */
  readonly frameLog: number[] = []
  frameLogLimit = 600

  constructor(canvas: HTMLCanvasElement, params: OrbParams = DEFAULT_ORB_PARAMS) {
    this.canvas = canvas
    this.renderer = new OrbRenderer(canvas, { powerPreference: 'low-power' })
    this.params = params
    // Waveform slot count follows the canvas aspect (a wide mount gets more bars
    // than a square one). The backing store is set before the animator is built.
    this.aspect = canvas.width > 0 && canvas.height > 0 ? canvas.width / canvas.height : 1
    this.slotCount = slotCountForAspect(this.aspect)
    this.waveDisplay = new Float32Array(this.slotCount)
    this.stateChangedAt = this.now()
    // Context-loss resilience: Windows GPUs really do drop the WebGL context
    // (driver resets, TDR, sleep/wake). Without recovery the orb would throw on
    // the dead context and stay blank forever; instead we pause on loss and
    // rebuild the renderer (recompiling shaders) when the browser restores it.
    canvas.addEventListener('webglcontextlost', this.onContextLost)
    canvas.addEventListener('webglcontextrestored', this.onContextRestored)
    // Start the loop immediately (found by the throttle harness: without this
    // an animator constructed in its default state never rendered a frame).
    this.kick()
  }

  private onContextLost = (e: Event): void => {
    // preventDefault is REQUIRED, or the browser never fires contextrestored.
    e.preventDefault()
    this.contextLost = true
    this.stop()
  }

  private onContextRestored = (): void => {
    try {
      // Fresh context on the same canvas — recompiles the shader program. The
      // animator keeps its logical state, so the orb resumes where it left off.
      this.renderer = new OrbRenderer(this.canvas, { powerPreference: 'low-power' })
      this.contextLost = false
      this.kick()
    } catch (err) {
      console.warn('[orb] context restore failed:', err)
    }
  }

  private now(): number {
    return performance.now() / 1000 - this.epoch
  }

  setState(state: OrbState): void {
    if (state === this.state) return
    // Capture the merge currently on screen (computed from the OUTGOING state,
    // carrying any in-progress cross-fade) so the new state's ramp starts from
    // it — the blob morphs continuously across the switch instead of snapping.
    this.enterMerge = mergeAmount(
      this.state,
      this.now() - this.stateChangedAt,
      this.speechMerge,
      this.enterMerge
    )
    this.state = state
    this.stateChangedAt = this.now()
    // Re-arm the entry whirl: its decay clock re-anchors to when the ring next
    // re-forms (see anchorWhirlStart), so a speaking→thinking whirl fires on the
    // visible ring rather than during the still-rolling-up line.
    this.whirlStartAt = null
    // 'speaking' as a STATE opens the speech gate; any other state closes it
    // (the envelope then dissolves smoothly). Callers using 'listening' +
    // ambient VAD signals re-open it via setSpeechActive AFTER setState.
    this.speechActive = state === 'speaking'
    this.kick()
  }

  /** Real speech signal (VAD gate / PTT capturing / live segments). May be used
   *  with state 'listening' for ambient capture, or implied by 'speaking'. */
  setSpeechActive(active: boolean): void {
    if (this.speechActive === active) return
    this.speechActive = active
    this.kick()
  }

  /** RAW live level ≥ 0 (hot input tolerated — shaped downstream). */
  setAmplitude(a: number): void {
    this.rawAmplitude = Math.max(0, a)
  }

  /** Play the genesis spring (materialize from scale 0). */
  summon(): void {
    this.summonedAt = this.now()
    this.kick()
  }

  /** Play the "failed voice turn" gesture — a brief damped horizontal tremor of
   *  the whole orb (see choreography.failTremorOffset). Re-stamps on each call so
   *  a repeated failure replays from the top. */
  failGesture(): void {
    this.failedAt = this.now()
    this.kick()
  }

  /** Drive the disc↔rounded-rect morph (0 = disc, 1 = expanded rect). */
  setMorphTarget(target: 0 | 1, rect: OrbRect = DEFAULT_MORPH_RECT): void {
    this.morphTarget = target
    this.rect = rect
    this.kick()
  }

  /** 0fps when hidden — stops the loop entirely. */
  setVisible(visible: boolean): void {
    if (this.visible === visible) return
    this.visible = visible
    if (visible) this.kick()
    else this.stop()
  }

  private isActive(): boolean {
    if (this.state !== 'idle' && this.state !== 'listening') return true
    if (this.speechActive || this.speechMerge > 0) return true
    if (this.morph !== this.morphTarget) return true
    if (this.summonedAt !== null && !genesisSettled(this.now() - this.summonedAt, this.params)) {
      return true
    }
    // The fail tremor is a fixed-length one-shot: keep the loop at 60fps until it
    // settles (u>=1), the same way genesis holds the loop while its spring rings.
    if (this.failedAt !== null && this.now() - this.failedAt < FAIL_GESTURE_MS / 1000) {
      return true
    }
    // A state change's settle is still animating: the merge cross-fade (e.g. the
    // blob dissolving back to the ring after thinking) or the spin-speed ease
    // into idle. Render those at 60fps too, matching the speech dissolve above.
    const stateTime = this.now() - this.stateChangedAt
    const steadyMerge = mergeAmount(this.state, Number.MAX_SAFE_INTEGER, this.speechMerge)
    const curMerge = mergeAmount(this.state, stateTime, this.speechMerge, this.enterMerge)
    if (Math.abs(curMerge - steadyMerge) > 0.005) return true
    if (Math.abs(this.spinMult - spinTargetFor(this.state, stateTime, this.params)) > 0.01) {
      return true
    }
    if (Math.abs(this.flow - orbitFlowFor(this.state)) > 0.01) return true
    return false
  }

  private stop(): void {
    if (this.raf !== null) cancelAnimationFrame(this.raf)
    this.raf = null
  }

  private kick(): void {
    if (!this.visible || this.contextLost || this.raf !== null) return
    this.raf = requestAnimationFrame(this.tick)
  }

  private tick = (nowMs: number): void => {
    this.raf = null
    if (!this.visible || this.contextLost) return
    const fps = this.isActive() ? ACTIVE_FPS : IDLE_FPS
    const minGap = 1000 / fps - 2 // small tolerance so 60Hz vsync isn't halved
    if (nowMs - this.lastFrameAt >= minGap) {
      this.lastFrameAt = nowMs
      this.renderFrame()
      this.frameLog.push(nowMs)
      if (this.frameLog.length > this.frameLogLimit) {
        this.frameLog.splice(0, this.frameLog.length - this.frameLogLimit)
      }
    }
    this.raf = requestAnimationFrame(this.tick)
  }

  private renderFrame(): void {
    const t = this.now()
    const dt = Math.max(0, Math.min(0.1, t - this.lastTime))
    this.lastTime = t
    // Deterministic envelope steps (same functions the harness scrubs with).
    this.speechMerge = stepMergeEnvelope(this.speechMerge, this.speechActive ? 1 : 0, dt)
    this.ampEnvelope = stepAmplitudeEnvelope(this.ampEnvelope, this.rawAmplitude, dt)
    // Waveform history: scroll a fresh loudness sample in at a fixed cadence
    // (steady scroll regardless of fps), then ease the displayed bar levels toward
    // the last `slotCount` samples so no bar height snaps in a single frame. When
    // the speech gate is fully closed, reset to silence so a later re-open never
    // flashes stale bars.
    const waveLevels = this.stepWaveform(dt)
    // The dot→bar handoff is no longer a separately-stepped gain here: it is the
    // UPPER staging band of the same speech-merge envelope (see barResponseFor /
    // AUDIO_STAGE_SPLIT), derived inside computeOrbFrame. That keeps entry and exit
    // exact mirrors and means the deterministic harness — which steps the identical
    // envelope — reproduces the live bar staging with nothing left to mirror.
    // Ease the orbit-speed multiplier toward the state's (whirl-shaped) target
    // and integrate the warped orbit clock (incremental → no angle jump when the
    // speed changes). The target itself carries the entry whirl (a decaying
    // overshoot), so the ring whirls fast on entry and eases to cruise.
    const stateTime = t - this.stateChangedAt
    // Anchor the entry-whirl to the ring re-forming: while the waveform line is
    // still rolling back up (waveMix ≥ eps) the whirl stays primed at full
    // overshoot; the frame the ring is formed it latches, and the fast spin then
    // decays on the VISIBLE ring. Non-whirl states fall through to stateTime.
    const isWhirl = this.state === 'thinking' || this.state === 'agents'
    const waveMix = waveMixFor(this.state, this.speechMerge)
    this.whirlStartAt = anchorWhirlStart(this.whirlStartAt, isWhirl, t, waveMix)
    const whirlTime = isWhirl ? (this.whirlStartAt === null ? 0 : t - this.whirlStartAt) : stateTime
    const spinTarget = spinTargetFor(this.state, stateTime, this.params, whirlTime)
    this.spinMult += (spinTarget - this.spinMult) * (1 - Math.exp(-dt / SPIN_EASE_TAU))
    this.orbitTime += dt * this.spinMult
    // Ease the orbit cadence toward the state's target (step-rest ↔ glide) so the
    // busy-state continuous spin fades in/out instead of snapping the motion.
    this.flow += (orbitFlowFor(this.state) - this.flow) * (1 - Math.exp(-dt / FLOW_EASE_TAU))
    // Ease the morph toward its target at a fixed rate (deterministic per dt).
    const step = dt / MORPH_SECONDS
    if (this.morph < this.morphTarget) this.morph = Math.min(this.morphTarget, this.morph + step)
    else if (this.morph > this.morphTarget) {
      this.morph = Math.max(this.morphTarget, this.morph - step)
    }
    const frame = computeOrbFrame({
      t,
      state: this.state,
      stateTime,
      amplitude: this.ampEnvelope,
      speechMerge: this.speechMerge,
      enterMerge: this.enterMerge,
      orbitTime: this.orbitTime,
      flow: this.flow,
      genesisTime: this.summonedAt === null ? Infinity : t - this.summonedAt,
      failedAt: this.failedAt ?? undefined,
      // Linear progress internally; eased at the point of use so the shape
      // change reads as one smooth motion in both directions.
      morph: easeInOut(this.morph),
      waveLevels,
      aspect: this.aspect,
      params: this.params
    })
    this.renderer.render(frame, this.rect)
  }

  /** Advance the waveform history/display for this frame and return the per-slot
   *  levels (empty when the row is idle so the choreography skips the bars). */
  private stepWaveform(dt: number): number[] | undefined {
    const gateOpen = this.speechActive || this.speechMerge > 0
    if (!gateOpen) {
      // Rest to silence between utterances (cheap; keeps the next open clean).
      if (this.waveWrite !== 0 || this.wavePushAccum !== 0) {
        this.waveHistory.fill(0)
        this.waveDisplay.fill(0)
        this.waveWrite = 0
        this.wavePushAccum = 0
      }
      return undefined
    }
    this.wavePushAccum += dt
    // Cap catch-up so a long stall (tab throttled) can't push hundreds of samples.
    // Each sample is run through the sensitivity curve (shapeBarLevel) so moderate
    // speech reads mid-height and loud never pins the bars at the max.
    let pushes = 0
    while (this.wavePushAccum >= WAVE_SAMPLE_SEC && pushes < WAVE_MAX_SLOTS) {
      this.waveWrite = historyPush(
        this.waveHistory,
        this.waveWrite,
        shapeBarLevel(this.ampEnvelope)
      )
      this.wavePushAccum -= WAVE_SAMPLE_SEC
      pushes++
    }
    const target = historySlots(this.waveHistory, this.waveWrite, this.slotCount)
    stepWaveLevels(this.waveDisplay, target, dt)
    return Array.from(this.waveDisplay)
  }

  dispose(): void {
    this.stop()
    this.canvas.removeEventListener('webglcontextlost', this.onContextLost)
    this.canvas.removeEventListener('webglcontextrestored', this.onContextRestored)
    this.renderer.dispose()
  }
}
