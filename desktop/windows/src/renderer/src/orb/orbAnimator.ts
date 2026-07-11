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
  stepMergeEnvelope,
  stepAmplitudeEnvelope,
  SPIN_EASE_TAU,
  DEFAULT_ORB_PARAMS,
  type OrbParams,
  type OrbState
} from './choreography'
import { OrbRenderer, DEFAULT_MORPH_RECT, type OrbRect } from './orbRenderer'

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
  private summonedAt: number | null = null
  private morphTarget = 0
  private morph = 0
  /** Raw live level target (from the mic pipeline) and its smoothed envelope. */
  private rawAmplitude = 0
  private ampEnvelope = 0
  /** Speech-merge envelope: eases to 1 while speech is active, dissolves to 0. */
  private speechActive = false
  private speechMerge = 0
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
    // A state change's settle is still animating: the merge cross-fade (e.g. the
    // blob dissolving back to the ring after thinking) or the spin-speed ease
    // into idle. Render those at 60fps too, matching the speech dissolve above.
    const stateTime = this.now() - this.stateChangedAt
    const steadyMerge = mergeAmount(this.state, Number.MAX_SAFE_INTEGER, this.speechMerge)
    const curMerge = mergeAmount(this.state, stateTime, this.speechMerge, this.enterMerge)
    if (Math.abs(curMerge - steadyMerge) > 0.005) return true
    if (Math.abs(this.spinMult - spinTargetFor(this.state, this.params)) > 0.01) return true
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
    // Ease the orbit-speed multiplier toward the state's target and integrate
    // the warped orbit clock (incremental → no angle jump when speed changes).
    const spinTarget = spinTargetFor(this.state, this.params)
    this.spinMult += (spinTarget - this.spinMult) * (1 - Math.exp(-dt / SPIN_EASE_TAU))
    this.orbitTime += dt * this.spinMult
    // Ease the morph toward its target at a fixed rate (deterministic per dt).
    const step = dt / MORPH_SECONDS
    if (this.morph < this.morphTarget) this.morph = Math.min(this.morphTarget, this.morph + step)
    else if (this.morph > this.morphTarget) {
      this.morph = Math.max(this.morphTarget, this.morph - step)
    }
    const frame = computeOrbFrame({
      t,
      state: this.state,
      stateTime: t - this.stateChangedAt,
      amplitude: this.ampEnvelope,
      speechMerge: this.speechMerge,
      enterMerge: this.enterMerge,
      orbitTime: this.orbitTime,
      genesisTime: this.summonedAt === null ? Infinity : t - this.summonedAt,
      // Linear progress internally; eased at the point of use so the shape
      // change reads as one smooth motion in both directions.
      morph: easeInOut(this.morph),
      params: this.params
    })
    this.renderer.render(frame, this.rect)
  }

  dispose(): void {
    this.stop()
    this.canvas.removeEventListener('webglcontextlost', this.onContextLost)
    this.canvas.removeEventListener('webglcontextrestored', this.onContextRestored)
    this.renderer.dispose()
  }
}
