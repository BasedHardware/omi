// Standalone orb harness — the deterministic development surface for the orb
// shader. Plain Chromium page (no Electron, no React): the driver scripts under
// scripts/orb/ build this with vite, serve it, and drive `window.orb` via
// Playwright. Time is ALWAYS injected: `renderAt` takes an explicit t and
// renders exactly one frame, so every check (readPixels invariants, motion
// profile, contact sheet) is reproducible pixel-for-pixel.
//
// URL params:
//   size=<px>      canvas CSS size (default 96)
//   dpr=<n>        device-pixel-ratio override (default real DPR)
//   preset=<name>  choreography preset (default/calm/lively/notch)
//   state=<s>      initial state (idle/listening/thinking/agents)
//   t=<sec>        initial time to render
//   live=1         run the self-throttled OrbAnimator instead (perf checks)
//   bg=checker     checkerboard page background (transparency review)
import './style.css'
import {
  computeOrbFrame,
  mergeAmount,
  spinTargetFor,
  stepMergeEnvelope,
  SPIN_EASE_TAU,
  ORB_PRESETS,
  DEFAULT_ORB_PARAMS,
  type OrbParams,
  type OrbState
} from '../src/renderer/src/orb/choreography'
import { OrbRenderer, DEFAULT_MORPH_RECT, type OrbRect } from '../src/renderer/src/orb/orbRenderer'
import { OrbAnimator } from '../src/renderer/src/orb/orbAnimator'

type RenderSpec = {
  t: number
  state?: OrbState
  stateTime?: number
  /** RAW voice level (shaped/bounded inside choreography). */
  amplitude?: number
  /** Speech-merge envelope 0..1 (the caller scrubs it deterministically). */
  speechMerge?: number
  /** Merge captured at state entry — drives the cross-fade (C6). */
  enterMerge?: number
  /** Warped orbit clock (C9 spin speed). Falls back to t. */
  orbitTime?: number
  /** Use the built-in deterministic voice demo timeline: speech starts at
   *  VOICE_T0, ends at VOICE_T1; amplitude follows a syllable-like envelope.
   *  Overrides amplitude/speechMerge from `t`. */
  voiceDemo?: boolean
  genesisTime?: number
  morph?: number
  preset?: string
  params?: Partial<OrbParams>
  rect?: OrbRect
}

// --- Deterministic recorded "voice" (closed-form, scrubbable) -----------------
const VOICE_T0 = 1.0
const VOICE_T1 = 5.0
const clamp01 = (x: number): number => Math.min(1, Math.max(0, x))

/** Syllable-ish amplitude envelope: sum of hann bumps at ~3.2Hz, plus a slow
 *  phrase contour. Purely a function of t. */
export function demoVoice(t: number): { amplitude: number; speechMerge: number } {
  // Attack (0.45s) after onset minus release (0.85s) after end — the same
  // shape stepMergeEnvelope converges to for this timeline.
  const speechMerge = Math.min(clamp01((t - VOICE_T0) / 0.45), 1 - clamp01((t - VOICE_T1) / 0.85))
  let amplitude = 0
  if (t >= VOICE_T0 && t <= VOICE_T1) {
    const u = t - VOICE_T0
    const syllable = 0.5 - 0.5 * Math.cos(2 * Math.PI * 3.2 * u)
    const phrase = 0.55 + 0.45 * Math.sin((u / (VOICE_T1 - VOICE_T0)) * Math.PI)
    amplitude = syllable * phrase
  }
  return { amplitude, speechMerge }
}

/** base64-encode an RGBA readback so it can cross page.evaluate. */
function encodePixels(bytes: Uint8Array): string {
  let bin = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(bin)
}

/** Count of white-blob pixels (bright + opaque) in an RGBA readback — the
 *  rendered silhouette area the transition check tracks for snap discontinuities. */
function whiteArea(rgba: Uint8Array): number {
  let n = 0
  for (let i = 0; i < rgba.length; i += 4) {
    if (rgba[i + 3] > 128 && rgba[i] > 200 && rgba[i + 1] > 200 && rgba[i + 2] > 200) n++
  }
  return n
}

const qs = new URLSearchParams(location.search)
const size = Number(qs.get('size') ?? 96)
const dpr = Number(qs.get('dpr') ?? window.devicePixelRatio ?? 1)
if (qs.get('bg') === 'checker') document.body.classList.add('checker')

const canvas = document.getElementById('orb') as HTMLCanvasElement
canvas.style.width = `${size}px`
canvas.style.height = `${size}px`
canvas.width = Math.round(size * dpr)
canvas.height = Math.round(size * dpr)

function resolveParams(spec: RenderSpec): OrbParams {
  const base = ORB_PRESETS[spec.preset ?? qs.get('preset') ?? 'default'] ?? DEFAULT_ORB_PARAMS
  return spec.params ? { ...base, ...spec.params } : base
}

const api = {
  presets: Object.keys(ORB_PRESETS),
  renderer: null as OrbRenderer | null,
  animator: null as OrbAnimator | null,

  /** Render exactly one deterministic frame. */
  renderAt(spec: RenderSpec): void {
    if (!this.renderer) this.renderer = new OrbRenderer(canvas)
    const demo = spec.voiceDemo ? demoVoice(spec.t) : null
    const frame = computeOrbFrame({
      t: spec.t,
      state: spec.state ?? (qs.get('state') as OrbState) ?? 'idle',
      stateTime: spec.stateTime ?? spec.t,
      amplitude: demo?.amplitude ?? spec.amplitude,
      speechMerge: demo?.speechMerge ?? spec.speechMerge,
      enterMerge: spec.enterMerge,
      orbitTime: spec.orbitTime,
      genesisTime: spec.genesisTime,
      morph: spec.morph,
      params: resolveParams(spec)
    })
    this.renderer.render(frame, spec.rect ?? DEFAULT_MORPH_RECT)
  },

  /**
   * Drive a deterministic state-change timeline the way the app's OrbAnimator
   * does — step the speech-merge envelope, capture `enterMerge` on the switch,
   * ease the spin multiplier, integrate the warped orbit clock — rendering each
   * frame and returning per-frame merge value + rendered white-blob area. The
   * C6 regression check asserts neither jumps frame-to-frame (a snap = an
   * explode-and-reform). Mirrors OrbAnimator.renderFrame/setState exactly.
   */
  transitionAreas(opts: {
    from: OrbState
    to: OrbState
    switchAt: number
    frames: number
    dt?: number
    fromSpeechActive?: boolean
    toSpeechActive?: boolean
    amplitude?: number
    preset?: string
  }): { merges: number[]; areas: number[] } {
    if (!this.renderer) this.renderer = new OrbRenderer(canvas)
    const params = resolveParams({ t: 0, preset: opts.preset })
    const dt = opts.dt ?? 1 / 60
    // The `from` state begins fully SETTLED (entered WARMUP seconds ago), so the
    // window shows the real transition — not a spurious gather from entering the
    // from-state at t=0 (e.g. thinking freshly ramping 0→1 before it dissolves).
    const WARMUP = 2
    let state = opts.from
    let stateChangedAt = -WARMUP
    let speechActive = opts.fromSpeechActive ?? opts.from === 'speaking'
    let speechMerge = speechActive ? 1 : 0 // start settled for the `from` state
    let enterMerge = mergeAmount(state, WARMUP, speechMerge)
    let spinMult = spinTargetFor(state, WARMUP, params)
    let orbitTime = 0
    const merges: number[] = []
    const areas: number[] = []
    for (let i = 0; i < opts.frames; i++) {
      const t = i * dt
      if (i > 0 && t >= opts.switchAt && state === opts.from) {
        // The setState moment: capture the merge currently shown, then switch.
        enterMerge = mergeAmount(state, t - stateChangedAt, speechMerge, enterMerge)
        state = opts.to
        stateChangedAt = t
        speechActive = opts.toSpeechActive ?? opts.to === 'speaking'
      }
      speechMerge = stepMergeEnvelope(speechMerge, speechActive ? 1 : 0, dt)
      const stateTime = t - stateChangedAt
      const spinTarget = spinTargetFor(state, stateTime, params)
      spinMult += (spinTarget - spinMult) * (1 - Math.exp(-dt / SPIN_EASE_TAU))
      orbitTime += dt * spinMult
      const frame = computeOrbFrame({
        t,
        state,
        stateTime,
        amplitude: opts.amplitude,
        speechMerge,
        enterMerge,
        orbitTime,
        params
      })
      this.renderer.render(frame, DEFAULT_MORPH_RECT)
      merges.push(frame.merge)
      areas.push(whiteArea(this.renderer.readPixels()))
    }
    return { merges, areas }
  },

  /** Same real-timeline drive as transitionAreas, but returns `count` evenly
   *  sampled rendered frames (base64 RGBA) spanning the switch — for the
   *  skeptical visual review of state-change continuity. */
  transitionFrames(opts: {
    from: OrbState
    to: OrbState
    switchAt: number
    duration: number
    count: number
    amplitude?: number
    preset?: string
  }): { width: number; height: number; frames: string[] } {
    if (!this.renderer) this.renderer = new OrbRenderer(canvas)
    const params = resolveParams({ t: 0, preset: opts.preset })
    const dt = 1 / 120
    const total = Math.round(opts.duration / dt)
    const sampleAt = new Set(
      Array.from({ length: opts.count }, (_, k) => Math.round((k / (opts.count - 1)) * (total - 1)))
    )
    // See transitionAreas: the `from` state starts settled (entered WARMUP ago).
    const WARMUP = 2
    let state = opts.from
    let stateChangedAt = -WARMUP
    let speechActive = opts.from === 'speaking'
    let speechMerge = speechActive ? 1 : 0
    let enterMerge = mergeAmount(state, WARMUP, speechMerge)
    let spinMult = spinTargetFor(state, WARMUP, params)
    let orbitTime = 0
    const frames: string[] = []
    for (let i = 0; i < total; i++) {
      const t = i * dt
      if (i > 0 && t >= opts.switchAt && state === opts.from) {
        enterMerge = mergeAmount(state, t - stateChangedAt, speechMerge, enterMerge)
        state = opts.to
        stateChangedAt = t
        speechActive = opts.to === 'speaking'
      }
      speechMerge = stepMergeEnvelope(speechMerge, speechActive ? 1 : 0, dt)
      spinMult +=
        (spinTargetFor(state, t - stateChangedAt, params) - spinMult) *
        (1 - Math.exp(-dt / SPIN_EASE_TAU))
      orbitTime += dt * spinMult
      const frame = computeOrbFrame({
        t,
        state,
        stateTime: t - stateChangedAt,
        amplitude: opts.amplitude,
        speechMerge,
        enterMerge,
        orbitTime,
        params
      })
      this.renderer.render(frame, DEFAULT_MORPH_RECT)
      if (sampleAt.has(i)) frames.push(encodePixels(this.renderer.readPixels()))
    }
    return { width: canvas.width, height: canvas.height, frames }
  },

  /** RGBA readback of the last rendered frame (base64 so it crosses evaluate). */
  pixels(): { width: number; height: number; data: string } {
    if (!this.renderer) throw new Error('renderAt first')
    return { width: canvas.width, height: canvas.height, data: encodePixels(this.renderer.readPixels()) }
  },

  // --- Live mode (perf/throttle checks; uses the app's real OrbAnimator) -----
  startLive(state: OrbState = 'idle'): void {
    if (!this.animator) this.animator = new OrbAnimator(canvas)
    this.animator.setState(state)
  },
  liveSetState(state: OrbState): void {
    this.animator?.setState(state)
  },
  liveSetSpeechActive(active: boolean): void {
    this.animator?.setSpeechActive(active)
  },
  liveSetAmplitude(a: number): void {
    this.animator?.setAmplitude(a)
  },
  liveSetVisible(visible: boolean): void {
    this.animator?.setVisible(visible)
  },
  liveSummon(): void {
    this.animator?.summon()
  },
  liveFrameLog(): number[] {
    return this.animator ? [...this.animator.frameLog] : []
  },
  liveClearLog(): void {
    this.animator?.frameLog.splice(0)
  }
}

declare global {
  interface Window {
    orb: typeof api
  }
}
window.orb = api

// Initial paint so a human opening the page sees something.
if (qs.get('live') === '1') {
  api.startLive((qs.get('state') as OrbState) ?? 'idle')
} else {
  api.renderAt({ t: Number(qs.get('t') ?? 1.2) })
}
