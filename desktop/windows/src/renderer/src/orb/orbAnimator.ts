// Self-throttled animation driver for the orb in the APP (the harness never
// uses this — it scrubs time directly). Owns the clock and the rAF loop:
//   idle           → 30fps
//   active states  → 60fps (listening / thinking / agents, genesis, morph)
//   hidden         → 0fps (loop fully stopped — the orb must cost nothing)
// Frame timestamps can be logged (OrbAnimator.frameLog) so the throttle states
// are assertable by the perf harness.
import {
  computeOrbFrame,
  easeInOut,
  genesisSettled,
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
  private amplitude = 0
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
  }

  private now(): number {
    return performance.now() / 1000 - this.epoch
  }

  setState(state: OrbState): void {
    if (state === this.state) return
    this.state = state
    this.stateChangedAt = this.now()
    this.kick()
  }

  setAmplitude(a: number): void {
    this.amplitude = Math.min(1, Math.max(0, a))
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
    if (this.state !== 'idle') return true
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
    const dt = Math.max(0, t - this.lastTime)
    this.lastTime = t
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
      amplitude: this.amplitude,
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
