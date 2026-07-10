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
// States (amended per Chris 2026-07-10: the merge-into-blob IS the speech
// visualization — the blob is the person's voice made visible):
//   idle       — slow orbit with ease-in-out steps (rotate → rest → resume).
//   listening  — quiet listening: same calm orbit (the mic is open, nothing
//                is being said). Visually restrained on purpose.
//   speaking   — live speech: the dots travel inward (staggered sweep) and
//                conglomerate into the waving puddle blob; the wave/oscillation
//                is DRIVEN by the live voice amplitude (bounded — see
//                shapeAmplitude). Dissolves back out when speech ends (the
//                caller eases `speechMerge` down via stepMergeEnvelope).
//   thinking   — deliberately DISTINCT from the speech blob: a tighter,
//                faster, autonomous pulse with zero audio coupling.
//   agents     — dots pair up into four status pills (clean, understated).
//
// Genesis (summon): scale 0 → full disc with an ease-out spring (slight
// overshoot, fast settle) — never a fade/slide of a full-size element.
// Morph: disc → rounded-rect is a single interpolation parameter consumed by
// the SDF shader (one shape, continuous).

export type OrbState = 'idle' | 'listening' | 'speaking' | 'thinking' | 'agents'

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
  /** Base blob edge wobble amplitude (fraction of disc radius). The speech
   *  wave scales this within WAVE_GAIN_MIN..WAVE_GAIN_MAX — bounded. */
  noiseAmp: number
  /** Blob wobble spatial frequency (cycles across the disc). */
  noiseFreq: number
  /** smin blend distance at full merge (fraction of disc radius). */
  sminK: number
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
  noiseAmp: 0.09,
  noiseFreq: 3.4,
  sminK: 0.34,
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
    noiseAmp: 0.06,
    sminK: 0.28
  },
  // Livelier: quicker steps, bigger wave.
  lively: {
    ...DEFAULT_ORB_PARAMS,
    orbitPeriod: 2.8,
    restFraction: 0.26,
    stepDegrees: 60,
    noiseAmp: 0.11,
    sminK: 0.4
  },
  // Tighter ring, smaller dots — closer to the Mac notch mark's proportions.
  notch: {
    ...DEFAULT_ORB_PARAMS,
    orbitRadius: 0.62,
    dotRadius: 0.085,
    orbitPeriod: 4.2
  },
  // For SMALL mounts (≤ ~28px: the bar pill, the sidebar brand spot): at that
  // size the default dots rasterize to ~1px and the anti-aliasing makes the
  // ring read as a loading spinner (skeptical-review finding). Proportionally
  // larger dots on a slightly tighter ring stay crisp.
  compact: {
    ...DEFAULT_ORB_PARAMS,
    orbitRadius: 0.54,
    dotRadius: 0.15,
    sminK: 0.3
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
   *  center mid-merge (found by the skeptical review). Pulses so the held
   *  blob oscillates instead of sitting as a static ball. */
  centerR: number
  /** Absolute wobble amplitude for the shader (disc units) — the speech wave.
   *  Bounded by construction: see shapeAmplitude + WAVE_GAIN_*. */
  waveAmp: number
  /** Shaped (bounded) amplitude 0..1 — the shader weights the finer noise
   *  octave with it so louder voice adds finer ripples. */
  amplitude: number
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

// --- Bounded amplitude (voice → wave, never spiky, never flatlined) -----------

/** The shaped amplitude never leaves [AMP_FLOOR, 1]: dead silence mid-speech
 *  keeps a visible minimum wobble, clipping input compresses to 1. */
export const AMP_FLOOR = 0.15
/** Wave gain (multiplier on params.noiseAmp) at shaped amplitude 0 and 1. */
export const WAVE_GAIN_MIN = 0.45
export const WAVE_GAIN_MAX = 1.6
/** Idle-blob (thinking) wave gain — fixed, no audio coupling. */
export const THINK_WAVE_GAIN = 0.5

/**
 * Soft-knee compression of a raw level into [AMP_FLOOR, 1]. tanh knee: linear-
 * ish at low levels, saturating toward 1 — arbitrary/clipping input can never
 * spike the wave past the designed maximum, and the floor keeps a live blob
 * from flatlining into a hard circle during momentary silence.
 */
export function shapeAmplitude(raw: number): number {
  const x = Math.max(0, raw)
  const DRIVE = 1.8
  const knee = Math.tanh(x * DRIVE) / Math.tanh(DRIVE)
  return AMP_FLOOR + (1 - AMP_FLOOR) * Math.min(1, knee)
}

/**
 * One deterministic smoothing step for the live level → envelope (fast attack,
 * slower release). Callers step it per frame with their dt; the harness can
 * replay recorded envelopes exactly.
 */
export function stepAmplitudeEnvelope(current: number, raw: number, dt: number): number {
  const target = Math.min(1.5, Math.max(0, raw)) // tolerate mildly hot input
  const tau = target > current ? 0.06 : 0.25
  return current + (target - current) * (1 - Math.exp(-dt / Math.max(1e-6, tau)))
}

/**
 * One deterministic step of the speech-merge envelope: eases toward 1 while
 * speech is active (VAD gate open / PTT capturing), and dissolves back toward
 * 0 (slower) when it ends. Linear internally; consumers shape with easeInOut.
 */
export function stepMergeEnvelope(current: number, target: 0 | 1, dt: number): number {
  const rate = target > current ? 1 / 0.45 : 1 / 0.85
  const next = current + Math.sign(target - current) * rate * dt
  return target > current ? Math.min(target, next) : Math.max(target, next)
}

/**
 * How merged the dots are (0 = ring, 1 = blob).
 * thinking: autonomous ramp to 1 over ~0.8s of state time, held.
 * speaking/listening/idle: driven entirely by the caller's speechMerge
 * envelope (speech signals). agents: 0.
 */
export function mergeAmount(state: OrbState, stateTime: number, speechMerge: number): number {
  if (state === 'thinking') return easeInOut(stateTime / 0.8)
  if (state === 'agents') return 0
  return easeInOut(Math.min(1, Math.max(0, speechMerge)))
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
  /** RAW voice level (≥ 0; may be hot/clipping — it is shaped internally). */
  amplitude?: number
  /** Speech-merge envelope 0..1 (stepMergeEnvelope output). Drives the blob
   *  for speaking/listening; ignored by thinking (autonomous) and agents. */
  speechMerge?: number
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
  const shaped = shapeAmplitude(input.amplitude ?? 0)
  const genesisTime = input.genesisTime ?? Infinity
  const merge = mergeAmount(state, stateTime, input.speechMerge ?? 0)
  const thinking = state === 'thinking'

  const angle = orbitAngle(t, p)

  // Merge travel is STAGGERED per dot (a rotational sweep: dots pool into the
  // puddle one after another and split back out the same way). A simultaneous
  // ring collapse left a punched hole at the center mid-merge (the smin union
  // of a ring is an annulus — skeptical-review Critical); staggering means
  // mass accumulates from the first arrivals, so the blob is solid throughout.
  const STAGGER = 0.5
  const dotMerge = (i: number): number =>
    Math.min(1, Math.max(0, merge * (1 + STAGGER) - STAGGER * (i / DOT_COUNT)))

  // Voice blob vs thinking blob — deliberately distinct characters:
  // speech = looser, slower pulse whose depth tracks the (bounded) voice;
  // thinking = tighter pool, faster autonomous pulse, no audio coupling.
  // Thinking pulses IN PHASE (no per-dot offset) and harder — per-dot phase
  // smearing made the radial sum nearly static (±0.7%, review round 3).
  const pulseFreq = thinking ? 4.6 : 2.3
  const pulseAmp = thinking ? 0.09 : 0.04 + 0.1 * shaped * merge
  const pulsePhase = (i: number): number => (thinking ? 0 : i * 1.7)

  // Agents pose: dot PAIRS converge onto the same center and stretch into one
  // capsule per row — identical superimposed primitives, so each pill is a
  // single clean bar (offset endpoints made lumpy dumbbells; review finding).
  // STAGED: the glide finishes BEFORE the stretch begins — stretching while
  // vertical neighbors were still in smooth-min range bridged pills across
  // rows into a two-row clump (review round 2). Dots glide as dots, settle on
  // their row centers, then lengthen into bars.
  const ap = state === 'agents' ? Math.min(1, Math.max(0, stateTime / 0.7)) : 0
  const agents = easeInOut(Math.min(1, ap / 0.6))
  const stretch = easeInOut(Math.max(0, (ap - 0.65) / 0.35))
  // Row assignment: each dot glides to the row matching its VERTICAL ORDER on
  // the ring at transition start (t - stateTime — deterministic). Index-fixed
  // pairing sent top-row dots straight through the second row's dots,
  // bridging pills mid-glide (review round 2).
  let rowOf: number[] | null = null
  if (ap > 0) {
    const a0 = orbitAngle(t - stateTime, p)
    const order = Array.from({ length: DOT_COUNT }, (_, i) => i).sort(
      (A, B) =>
        Math.sin(a0 + (A * 2 * Math.PI) / DOT_COUNT) - Math.sin(a0 + (B * 2 * Math.PI) / DOT_COUNT)
    )
    rowOf = new Array(DOT_COUNT)
    order.forEach((dotIdx, rank) => {
      rowOf![dotIdx] = Math.floor(rank / 2)
    })
  }

  const dots: OrbDot[] = []
  for (let i = 0; i < DOT_COUNT; i++) {
    const a = angle + (i * 2 * Math.PI) / DOT_COUNT
    const mi = dotMerge(i)
    const orbitRi = p.orbitRadius * (1 - mi)
    let x = Math.cos(a) * orbitRi
    let y = Math.sin(a) * orbitRi
    // Dots grow modestly as they pool (a puddle, not a giant ball — review
    // finding), with a gentle per-dot pulse so the held blob oscillates
    // organically instead of sitting as a static disc.
    let r =
      p.dotRadius * (1 + mi * 1.0) * (1 + pulseAmp * mi * Math.sin(t * pulseFreq + pulsePhase(i)))
    let halfLen = 0
    if (agents > 0 && rowOf) {
      const row = rowOf[i]
      const py = (row - 1.5) * p.pillRowPitch
      x = x * (1 - agents)
      y = y * (1 - agents) + py * agents
      r = r * (1 - agents) + p.dotRadius * 0.72 * agents
      halfLen = p.pillHalfLen * stretch
    }
    dots.push({ x, y, r, halfLen })
  }

  // Center pool: grows as the first dots arrive and breathes so the held blob
  // feels liquid. Gated below merge≈0.1 — a sub-pixel pool at the very start
  // of a merge reads as a stray white speck at the ring's center. The speech
  // pool swells slightly with the (bounded) voice; the thinking pool is
  // tighter with a quicker breath.
  const poolGate = easeInOut(Math.min(1, Math.max(0, (merge - 0.15) / 0.3)))
  const poolBase = thinking ? 0.34 : 0.42 * (0.92 + 0.14 * shaped)
  const poolPulse = thinking ? 0.13 * Math.sin(t * 4.6) : (0.07 + 0.05 * shaped) * Math.sin(t * 1.7)
  // Hard-zero below a visibility floor: smin INFLATES even a sub-pixel pool
  // into a faint center speck (review round 2), so the pool only exists once
  // it is genuinely visible; the smin blend masks the small pop.
  const rawPool = poolGate * p.orbitRadius * poolBase * (1 + poolPulse)
  const centerR = merge > 0 && rawPool > 0.02 ? rawPool : 0

  // The wave: bounded by construction. Speech maps the shaped amplitude into
  // [WAVE_GAIN_MIN, WAVE_GAIN_MAX]×noiseAmp; thinking uses a fixed lower gain.
  const waveAmp =
    p.noiseAmp *
    (thinking ? THINK_WAVE_GAIN : WAVE_GAIN_MIN + (WAVE_GAIN_MAX - WAVE_GAIN_MIN) * shaped)

  return {
    dots,
    merge,
    centerR,
    waveAmp,
    amplitude: shaped,
    morph: Math.min(1, Math.max(0, input.morph ?? 0)),
    genesis: genesisTime === Infinity ? 1 : genesisScale(genesisTime, p),
    noiseTime: t,
    params: p
  }
}
