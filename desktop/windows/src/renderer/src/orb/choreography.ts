// Orb choreography — ALL motion math for the Omi orb, as pure functions of an
// injected time. Nothing here reads a clock, touches the DOM, or knows about
// WebGL: `computeOrbFrame(t, …)` returns the full pose for that instant, so
// every frame is deterministic and scrubbable (the harness drives `t` directly;
// the app's OrbAnimator advances it with rAF). The shader (orbRenderer.ts) is a
// dumb rasterizer of the returned frame.
//
// Mark (decided by Chris 2026-07-10, do not revisit): 8 white dots on a dark
// disc, matching the Mac notch logo.
//
// States:
//   idle       — slow orbit with ease-in-out steps (rotate → rest → resume);
//                periodically the dots travel inward, growing, merging into an
//                oscillating "puddle" blob, then split back out.
//   listening  — the orbit subtly amplitude-synced (dot size + orbit breathe).
//   thinking   — dots merge into the held, oscillating blob.
//   agents     — dots pair up into four status pills (clean, understated).
//
// Genesis (summon): scale 0 → full disc with an ease-out spring (slight
// overshoot, fast settle) — never a fade/slide of a full-size element.
// Morph: disc → rounded-rect is a single interpolation parameter consumed by
// the SDF shader (one shape, continuous).

export type OrbState = 'idle' | 'listening' | 'thinking' | 'agents'

export const DOT_COUNT = 8

/** Tunable look/feel parameters. `ORB_PRESETS` holds the reviewed variants. */
export type OrbParams = {
  /** Disc radius as a fraction of the canvas half-extent. */
  discRadius: number
  /** Dot orbit radius as a fraction of the disc radius. */
  orbitRadius: number
  /** Dot radius as a fraction of the disc radius. */
  dotRadius: number
  /** One orbit step cycle (rotate + rest), seconds. */
  orbitPeriod: number
  /** Fraction of the cycle spent at rest (0..1). */
  restFraction: number
  /** Degrees the ring advances per cycle. */
  stepDegrees: number
  /** Idle merge excursion: period and duration, seconds. */
  mergePeriod: number
  mergeDuration: number
  /** Blob edge wobble amplitude (fraction of disc radius) at full merge. */
  noiseAmp: number
  /** Blob wobble spatial frequency (cycles across the disc). */
  noiseFreq: number
  /** smin blend distance at full merge (fraction of disc radius). */
  sminK: number
  /** Listening: max dot-size gain and orbit-radius breathe at amplitude 1. */
  listenSizeGain: number
  listenOrbitGain: number
  /** Agents: pill half-length (fraction of disc radius) and row pitch. */
  pillHalfLen: number
  pillRowPitch: number
  /** Genesis spring: damping ratio and natural frequency (rad/s). */
  springZeta: number
  springOmega: number
}

export const DEFAULT_ORB_PARAMS: OrbParams = {
  discRadius: 0.92,
  orbitRadius: 0.58,
  dotRadius: 0.095,
  orbitPeriod: 3.6,
  restFraction: 0.34,
  stepDegrees: 45,
  mergePeriod: 22,
  mergeDuration: 5.2,
  noiseAmp: 0.09,
  noiseFreq: 3.4,
  sminK: 0.34,
  listenSizeGain: 0.3,
  listenOrbitGain: 0.07,
  pillHalfLen: 0.22,
  pillRowPitch: 0.3,
  springZeta: 0.68,
  springOmega: 14
}

/** Named parameter variants kept for review/flipping in the harness. The
 *  default is the reviewed pick; runners-up stay selectable via ?preset=. */
export const ORB_PRESETS: Record<string, OrbParams> = {
  default: DEFAULT_ORB_PARAMS,
  // Calmer: slower steps, longer rests, softer blob.
  calm: {
    ...DEFAULT_ORB_PARAMS,
    orbitPeriod: 4.8,
    restFraction: 0.42,
    noiseAmp: 0.035,
    sminK: 0.28
  },
  // Livelier: quicker steps, bigger merge wobble.
  lively: {
    ...DEFAULT_ORB_PARAMS,
    orbitPeriod: 2.8,
    restFraction: 0.26,
    stepDegrees: 60,
    noiseAmp: 0.065,
    sminK: 0.4
  },
  // Tighter ring, smaller dots — closer to the Mac notch mark's proportions.
  notch: {
    ...DEFAULT_ORB_PARAMS,
    orbitRadius: 0.62,
    dotRadius: 0.085,
    orbitPeriod: 4.2
  }
}

/** One dot/pill primitive handed to the shader: center (normalized, disc
 *  units), radius, and capsule half-length (0 = circle). */
export type OrbDot = { x: number; y: number; r: number; halfLen: number }

/** Everything the shader needs for one frame. */
export type OrbFrame = {
  dots: OrbDot[]
  /** 0 = separate dots, 1 = fully merged blob (drives smin k + wobble). */
  merge: number
  /** Center pool-blob radius (disc units). Fills the middle while the ring of
   *  dots converges — without it the smin union leaves a punched hole at the
   *  center mid-merge (found by the skeptical review). Pulses gently while
   *  merged so the held blob oscillates instead of sitting as a static ball. */
  centerR: number
  /** Disc → rounded-rect morph, 0..1. */
  morph: number
  /** Genesis scale, 0..~1 (can overshoot slightly). */
  genesis: number
  /** Time feed for the shader's noise field (seconds). */
  noiseTime: number
  params: OrbParams
}

// --- Easing ------------------------------------------------------------------

/** Smootherstep — C2-continuous ease-in-out. v(0)=v(1)=0, single velocity peak
 *  at t=0.5 (the S-curve the motion-profile check asserts). */
export function easeInOut(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return x * x * x * (x * (x * 6 - 15) + 10)
}

/** d/dt of easeInOut — used by tests to assert the velocity S-curve. */
export function easeInOutVelocity(t: number): number {
  const x = Math.min(1, Math.max(0, t))
  return 30 * x * x * (x - 1) * (x - 1)
}

// --- Orbit -------------------------------------------------------------------

/**
 * Ring rotation angle (radians) at time t: per cycle the ring eases through
 * `stepDegrees` (velocity S-curve), then rests. Continuous across cycles.
 */
export function orbitAngle(t: number, p: OrbParams): number {
  const period = Math.max(1e-6, p.orbitPeriod)
  const cycle = Math.floor(t / period)
  const u = (t - cycle * period) / period
  const rotateFrac = 1 - Math.min(0.95, Math.max(0, p.restFraction))
  const progress = u < rotateFrac ? easeInOut(u / rotateFrac) : 1
  const step = (p.stepDegrees * Math.PI) / 180
  return (cycle + progress) * step
}

/** Instantaneous angular velocity (rad/s) — for the motion-profile check. */
export function orbitVelocity(t: number, p: OrbParams): number {
  const period = Math.max(1e-6, p.orbitPeriod)
  const u = (t - Math.floor(t / period) * period) / period
  const rotateFrac = 1 - Math.min(0.95, Math.max(0, p.restFraction))
  if (u >= rotateFrac) return 0
  const step = (p.stepDegrees * Math.PI) / 180
  return (easeInOutVelocity(u / rotateFrac) * step) / (rotateFrac * period)
}

// --- Merge (dots ↔ blob) -----------------------------------------------------

/** Shaped 0→1→0 bump used by the idle merge excursion: eases in over the first
 *  30%, holds, eases out over the last 30%. */
export function mergeBump(u: number): number {
  if (u <= 0 || u >= 1) return 0
  if (u < 0.3) return easeInOut(u / 0.3)
  if (u > 0.7) return easeInOut((1 - u) / 0.3)
  return 1
}

/**
 * How merged the dots are at time t (0 = ring, 1 = blob).
 * idle: periodic excursion (travel in, blob, split back out).
 * thinking: ramp to 1 over ~0.8s of state time and hold.
 * listening/agents: 0 (their own poses take over).
 */
export function mergeAmount(t: number, state: OrbState, stateTime: number, p: OrbParams): number {
  if (state === 'thinking') return easeInOut(stateTime / 0.8)
  if (state !== 'idle') return 0
  const phase = ((t % p.mergePeriod) + p.mergePeriod) % p.mergePeriod
  return mergeBump(phase / Math.max(1e-6, p.mergeDuration))
}

// --- Genesis spring ----------------------------------------------------------

/**
 * Under-damped spring 0 → 1 (closed form), ζ from params: fast ease-out with a
 * slight (~3–5%) overshoot then settle. Clamped at ≥ 0. This is the "materialize
 * from nothing" scale — never used as a fade.
 */
export function genesisScale(tSinceSummon: number, p: OrbParams = DEFAULT_ORB_PARAMS): number {
  if (tSinceSummon <= 0) return 0
  const z = p.springZeta
  const w = p.springOmega
  const wd = w * Math.sqrt(Math.max(1e-6, 1 - z * z))
  const decay = Math.exp(-z * w * tSinceSummon)
  const s = 1 - decay * (Math.cos(wd * tSinceSummon) + ((z * w) / wd) * Math.sin(wd * tSinceSummon))
  return Math.max(0, s)
}

/** True once the genesis spring has visually settled (within 1% of rest). */
export function genesisSettled(tSinceSummon: number, p: OrbParams = DEFAULT_ORB_PARAMS): boolean {
  // Envelope bound: decay * (1 + z w / wd) < 1% → settled regardless of phase.
  const z = p.springZeta
  const w = p.springOmega
  const wd = w * Math.sqrt(Math.max(1e-6, 1 - z * z))
  return Math.exp(-z * w * tSinceSummon) * (1 + (z * w) / wd) < 0.01
}

// --- Frame assembly ----------------------------------------------------------

export type OrbInputs = {
  /** Global animation time, seconds (injected — never a live clock). */
  t: number
  state: OrbState
  /** Seconds since `state` was entered (drives state transitions). */
  stateTime: number
  /** Voice amplitude 0..1 (listening state). */
  amplitude?: number
  /** Seconds since summon, or Infinity when long-since materialized. */
  genesisTime?: number
  /** Disc → rounded-rect morph 0..1 (expanded surface drives this). */
  morph?: number
  params?: OrbParams
}

/** Compute the full pose for one frame. Pure and deterministic. */
export function computeOrbFrame(input: OrbInputs): OrbFrame {
  const p = input.params ?? DEFAULT_ORB_PARAMS
  const { t, state, stateTime } = input
  const amplitude = Math.min(1, Math.max(0, input.amplitude ?? 0))
  const genesisTime = input.genesisTime ?? Infinity
  const merge = mergeAmount(t, state, stateTime, p)

  // Ring pose (idle / listening / thinking share the orbit; thinking pulls it in).
  const angle = orbitAngle(t, p)
  const breathe = state === 'listening' ? 1 + p.listenOrbitGain * amplitude : 1
  const sizeGain = state === 'listening' ? 1 + p.listenSizeGain * amplitude : 1

  // Merge travel is STAGGERED per dot (a rotational sweep: dots pool into the
  // puddle one after another and split back out the same way). A simultaneous
  // ring collapse left a punched hole at the center mid-merge (the smin union
  // of a ring is an annulus — skeptical-review Critical); staggering means
  // mass accumulates from the first arrivals, so the blob is solid throughout.
  const STAGGER = 0.5
  const dotMerge = (i: number): number =>
    Math.min(1, Math.max(0, merge * (1 + STAGGER) - STAGGER * (i / DOT_COUNT)))

  // Agents pose: dot PAIRS converge onto the same center and stretch into one
  // capsule per row — identical superimposed primitives, so each pill is a
  // single clean bar (offset endpoints made lumpy dumbbells; review finding).
  const agents = state === 'agents' ? easeInOut(stateTime / 0.7) : 0
  // Stretch late: dots glide as dots first, then lengthen into bars, which
  // keeps the transition legible instead of thrashing.
  const stretch = Math.pow(agents, 1.6)

  const dots: OrbDot[] = []
  for (let i = 0; i < DOT_COUNT; i++) {
    const a = angle + (i * 2 * Math.PI) / DOT_COUNT
    const mi = dotMerge(i)
    const orbitRi = p.orbitRadius * breathe * (1 - mi)
    let x = Math.cos(a) * orbitRi
    let y = Math.sin(a) * orbitRi
    // Dots grow modestly as they pool (a puddle, not a giant ball — review
    // finding), with a gentle per-dot pulse so the held blob oscillates
    // organically instead of sitting as a static disc.
    let r = p.dotRadius * sizeGain * (1 + mi * 1.0) * (1 + 0.07 * mi * Math.sin(t * 2.3 + i * 1.7))
    let halfLen = 0
    if (agents > 0) {
      const row = Math.floor(i / 2)
      const py = (row - 1.5) * p.pillRowPitch
      x = x * (1 - agents)
      y = y * (1 - agents) + py * agents
      r = r * (1 - agents) + p.dotRadius * 0.72 * agents
      halfLen = p.pillHalfLen * stretch
    }
    dots.push({ x, y, r, halfLen })
  }

  // Center pool: grows as the first dots arrive and breathes slowly so the
  // held blob feels liquid. Gated below merge≈0.1 — a sub-pixel pool at the
  // very start of a merge reads as a stray white speck at the ring's center.
  const poolGate = easeInOut(Math.min(1, Math.max(0, (merge - 0.1) / 0.25)))
  const centerR =
    merge > 0 ? poolGate * p.orbitRadius * 0.42 * (1 + 0.09 * Math.sin(t * 1.7)) : 0

  return {
    dots,
    merge,
    centerR,
    morph: Math.min(1, Math.max(0, input.morph ?? 0)),
    genesis: genesisTime === Infinity ? 1 : genesisScale(genesisTime, p),
    noiseTime: t,
    params: p
  }
}
