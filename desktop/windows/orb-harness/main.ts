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
  anchorWhirlStart,
  waveMixFor,
  stepMergeEnvelope,
  SPIN_EASE_TAU,
  ORB_PRESETS,
  DEFAULT_ORB_PARAMS,
  type OrbParams,
  type OrbState
} from '../src/renderer/src/orb/choreography'
import { slotCountForAspect } from '../src/renderer/src/orb/waveform'
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
  /** Scrolling waveform demo: fills waveLevels from a deterministic scrolling
   *  speech envelope (silence → burst → silence) sampled at `t`, and forces
   *  speechMerge to 1 (full waveform). Overrides waveLevels. */
  waveDemo?: boolean
  /** Explicit per-slot waveform levels 0..1 (oldest→newest). */
  waveLevels?: number[]
  /** Bar-response gain 0..1 (staged ramp-in after the unroll). Defaults to 1. */
  waveResponse?: number
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

// --- Deterministic scrolling waveform demo ------------------------------------
const WAVE_SAMPLE_SEC = 0.06

/** Speech loudness at absolute sample-time `s` (seconds): silence outside 1..5s,
 *  a syllable-modulated phrase inside. Pure. */
export function demoLoud(s: number): number {
  if (s < VOICE_T0 || s > VOICE_T1) return 0
  const u = s - VOICE_T0
  const syllable = 0.5 - 0.5 * Math.cos(2 * Math.PI * 2.5 * u)
  const phrase = 0.5 + 0.5 * Math.sin((u / (VOICE_T1 - VOICE_T0)) * Math.PI)
  return Math.min(1, syllable * phrase * 1.15)
}

/** Scrolling history window ending at time `t`: slot j (oldest→newest) samples
 *  the loudness `age` seconds before `t`, so the burst scrolls right→left. */
export function demoWaveLevels(t: number, slotCount: number): number[] {
  const out: number[] = []
  for (let j = 0; j < slotCount; j++) {
    const age = (slotCount - 1 - j) * WAVE_SAMPLE_SEC
    out.push(demoLoud(t - age))
  }
  return out
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

/** Alpha-weighted white MASS of an RGBA readback (premultiplied): sum of the red
 *  channel over pixels brighter than the dark disc. For a white dot/bar the
 *  premultiplied red equals its coverage×opacity, so this tracks the rendered
 *  ink CONTINUOUSLY across an opacity crossfade (a binary count would step as
 *  pixels cross a threshold — a metric artifact, not a real snap). The >40 cut
 *  excludes the near-black disc (premult red ≲ 22) so its invisible-on-the-pill
 *  fade doesn't register; the transition check tracks this for snap discontinuities. */
function whiteArea(rgba: Uint8Array): number {
  let sum = 0
  for (let i = 0; i < rgba.length; i += 4) {
    if (rgba[i] > 40) sum += rgba[i]
  }
  return sum
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

  /** Resize the harness canvas (CSS box + backing store). Aspect drives the
   *  waveform slot count, so wide vs mini evidence renders through the same API. */
  setCanvasSize(cssW: number, cssH: number, dprOverride?: number): void {
    const d = dprOverride ?? dpr
    canvas.style.width = `${cssW}px`
    canvas.style.height = `${cssH}px`
    canvas.width = Math.round(cssW * d)
    canvas.height = Math.round(cssH * d)
  },

  /** Render exactly one deterministic frame. */
  renderAt(spec: RenderSpec): void {
    if (!this.renderer) this.renderer = new OrbRenderer(canvas)
    const demo = spec.voiceDemo ? demoVoice(spec.t) : null
    const aspect = canvas.width / canvas.height
    let waveLevels = spec.waveLevels
    let speechMerge = demo?.speechMerge ?? spec.speechMerge
    if (spec.waveDemo) {
      waveLevels = demoWaveLevels(spec.t, slotCountForAspect(aspect))
      speechMerge = 1
    }
    const frame = computeOrbFrame({
      t: spec.t,
      state: spec.state ?? (qs.get('state') as OrbState) ?? 'idle',
      stateTime: spec.stateTime ?? spec.t,
      amplitude: demo?.amplitude ?? spec.amplitude,
      speechMerge,
      enterMerge: spec.enterMerge,
      orbitTime: spec.orbitTime,
      genesisTime: spec.genesisTime,
      morph: spec.morph,
      waveLevels,
      waveResponse: spec.waveResponse,
      aspect,
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
    /** Static per-slot waveform levels applied every frame — so the rendered area
     *  reflects the ring→waveform crossfade smoothly rather than a scroll. */
    waveLevels?: number[]
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
    let whirlStartAt: number | null = null
    const merges: number[] = []
    const areas: number[] = []
    for (let i = 0; i < opts.frames; i++) {
      const t = i * dt
      if (i > 0 && t >= opts.switchAt && state === opts.from) {
        // The setState moment: capture the merge currently shown, then switch.
        enterMerge = mergeAmount(state, t - stateChangedAt, speechMerge, enterMerge)
        state = opts.to
        stateChangedAt = t
        whirlStartAt = null // re-arm the whirl for the new state (see OrbAnimator)
        speechActive = opts.toSpeechActive ?? opts.to === 'speaking'
      }
      speechMerge = stepMergeEnvelope(speechMerge, speechActive ? 1 : 0, dt)
      const stateTime = t - stateChangedAt
      const isWhirl = state === 'thinking' || state === 'agents'
      whirlStartAt = anchorWhirlStart(whirlStartAt, isWhirl, t, waveMixFor(state, speechMerge))
      const whirlTime = isWhirl ? (whirlStartAt === null ? 0 : t - whirlStartAt) : stateTime
      const spinTarget = spinTargetFor(state, stateTime, params, whirlTime)
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
        waveLevels: opts.waveLevels,
        aspect: canvas.width / canvas.height,
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
    waveLevels?: number[]
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
    let whirlStartAt: number | null = null
    const frames: string[] = []
    for (let i = 0; i < total; i++) {
      const t = i * dt
      if (i > 0 && t >= opts.switchAt && state === opts.from) {
        enterMerge = mergeAmount(state, t - stateChangedAt, speechMerge, enterMerge)
        state = opts.to
        stateChangedAt = t
        whirlStartAt = null // re-arm the whirl for the new state (see OrbAnimator)
        speechActive = opts.to === 'speaking'
      }
      speechMerge = stepMergeEnvelope(speechMerge, speechActive ? 1 : 0, dt)
      const stateTime = t - stateChangedAt
      const isWhirl = state === 'thinking' || state === 'agents'
      whirlStartAt = anchorWhirlStart(whirlStartAt, isWhirl, t, waveMixFor(state, speechMerge))
      const whirlTime = isWhirl ? (whirlStartAt === null ? 0 : t - whirlStartAt) : stateTime
      spinMult +=
        (spinTargetFor(state, stateTime, params, whirlTime) - spinMult) *
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
        waveLevels: opts.waveLevels,
        aspect: canvas.width / canvas.height,
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
    return {
      width: canvas.width,
      height: canvas.height,
      data: encodePixels(this.renderer.readPixels())
    }
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
