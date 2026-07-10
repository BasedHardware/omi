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
  stepMergeEnvelope,
  stepAmplitudeEnvelope,
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
  private renderer: OrbRenderer
  private params: OrbParams
  private state: OrbState = 'idle'
  private stateChangedAt = 0
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
    this.renderer = new OrbRenderer(canvas, { powerPreference: 'low-power' })
    this.params = params
    this.stateChangedAt = this.now()
    // Start the loop immediately (found by the throttle harness: without this
    // an animator constructed in its default state never rendered a frame).
    this.kick()
  }

  private now(): number {
    return performance.now() / 1000 - this.epoch
  }

  setState(state: OrbState): void {
    if (state === this.state) return
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
    return false
  }

  private stop(): void {
    if (this.raf !== null) cancelAnimationFrame(this.raf)
    this.raf = null
  }

  private kick(): void {
    if (!this.visible || this.raf !== null) return
    this.raf = requestAnimationFrame(this.tick)
  }

  private tick = (nowMs: number): void => {
    this.raf = null
    if (!this.visible) return
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
    this.renderer.dispose()
  }
}
