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
//   thinking   — deliberately DISTINCT from the speech blob: the dots STAY
//                SEPARATE on the ring and orbit CONTINUOUSLY at an elevated
//                speed (merge-into-a-puddle is reserved for speech). Entry kicks
//                off a fast whirl that eases down to a steady cruise. Also covers
//                transcribing and a streaming reply (status 'sending').
//   agents     — entry whirls the ring fast for ~1s, THEN the dots pair up into
//                four status pills (clean, understated) while the agent runs.
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
  /** Orbit speed multiplier at the busiest state (thinking). Idle is always 1×;
   *  busy states target a fraction of the way to this, and the animator eases
   *  the live multiplier toward the target so the ring visibly spins up while
   *  Omi is working and slows as it settles. Kept lower on compact mounts so a
   *  22–26px orb never reads as frantic. */
  spinBusyMult: number
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
  springOmega: 14,
  spinBusyMult: 2.0
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
    sminK: 0.28,
    spinBusyMult: 1.7
  },
  // Livelier: quicker steps and spin. Wave amplitude stays in line with the
  // others — its own 0.11 combined with the wider wave-gain span tore the
  // merged silhouette into sharp inward notches (skeptical-review finding).
  lively: {
    ...DEFAULT_ORB_PARAMS,
    orbitPeriod: 2.8,
    restFraction: 0.26,
    stepDegrees: 60,
    noiseAmp: 0.092,
    sminK: 0.4,
    spinBusyMult: 2.3
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
    sminK: 0.3,
    // Restrained spin-up: at 22–26px a big multiplier reads as frantic.
    spinBusyMult: 1.55
  }
}

/** One dot/pill primitive handed to the shader: center (normalized, disc
 *  units), radius, capsule half-length (0 = circle), and this dot's own merge
 *  progress 0..1. The shader derives its smin blend distance PER DOT from
 *  `merge` so a dot that hasn't converged yet unions near-hard (no haze/webbing
 *  bridging it to still-separate neighbours); only converged dots blend into the
 *  liquid pool. A single global k applied to every pair is what produced the
 *  faint mist between mid-merge dots. */
export type OrbDot = { x: number; y: number; r: number; halfLen: number; merge: number }

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
 * Ring rotation angle (radians) at time t.
 *
 * `flow` (0..1) blends the cadence: 0 = eased STEP-then-REST (per cycle the ring
 * eases through `stepDegrees` then rests — the calm idle look); 1 = a CONTINUOUS
 * linear glide at the same average rate (the "dots moving around a circle fast"
 * look busy states need — a discrete stepping ring never reads as spinning). The
 * two agree exactly at every cycle boundary, so the blend is continuous across
 * cycles for any flow, and the average rate (one `stepDegrees` per period) is
 * identical either way — flow changes the texture of the motion, not its speed.
 */
export function orbitAngle(t: number, p: OrbParams, flow = 0): number {
  const period = Math.max(1e-6, p.orbitPeriod)
  const cycle = Math.floor(t / period)
  const u = (t - cycle * period) / period
  const rotateFrac = 1 - Math.min(0.95, Math.max(0, p.restFraction))
  const stepped = u < rotateFrac ? easeInOut(u / rotateFrac) : 1
  const f = Math.min(1, Math.max(0, flow))
  const progress = stepped * (1 - f) + u * f
  const step = (p.stepDegrees * Math.PI) / 180
  return (cycle + progress) * step
}

/** Instantaneous angular velocity (rad/s) — for the motion-profile check. At
 *  `flow` 1 it never rests (constant glide `step/period`); at 0 it is the eased
 *  step profile (0 → peak → 0, then a rest). */
export function orbitVelocity(t: number, p: OrbParams, flow = 0): number {
  const period = Math.max(1e-6, p.orbitPeriod)
  const u = (t - Math.floor(t / period) * period) / period
  const rotateFrac = 1 - Math.min(0.95, Math.max(0, p.restFraction))
  const step = (p.stepDegrees * Math.PI) / 180
  const f = Math.min(1, Math.max(0, flow))
  const steppedV =
    u >= rotateFrac ? 0 : (easeInOutVelocity(u / rotateFrac) * step) / (rotateFrac * period)
  const continuousV = step / period
  return steppedV * (1 - f) + continuousV * f
}

/**
 * Per-state orbit cadence: busy orbiting states (thinking, and the agents entry
 * whirl) glide the ring CONTINUOUSLY (1) so it reads as spinning fast; idle and
 * quiet listening keep the calm STEP-then-REST cadence (0). The animator eases
 * the live value across a state change so the cadence shift is never a jerk;
 * deterministic renders (harness/tests) fall back to this per-state default.
 */
export function orbitFlowFor(state: OrbState): number {
  return state === 'thinking' || state === 'agents' ? 1 : 0
}

/** Exponential time-constant (s) for easing the live orbit-cadence `flow` toward
 *  its state target — a smooth glide↔step crossover, no snap when it flips. */
export const FLOW_EASE_TAU = 0.3

// --- Bounded amplitude (voice → wave, never spiky, never flatlined) -----------

/** The shaped amplitude never leaves [AMP_FLOOR, 1]: dead silence mid-speech
 *  keeps a visible minimum wobble, clipping input compresses to 1. */
export const AMP_FLOOR = 0.15
/** Wave gain (multiplier on params.noiseAmp) at shaped amplitude 0 and 1. The
 *  min is low and the max high on purpose: a wide span is what makes a loud
 *  syllable read as a visibly bigger edge wave than a quiet one (C8b). Bounded —
 *  the orb:check 'wavy' invariant caps the loud end. */
export const WAVE_GAIN_MIN = 0.35
export const WAVE_GAIN_MAX = 1.85
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
  // Softer knee (was 1.8): less compression through the normal speaking range,
  // so quiet vs loud syllables land at distinct wave depths instead of both
  // saturating high — the orb visibly tracks the voice. Clipping still saturates
  // at 1 (bounded) and silence still rests at AMP_FLOOR (never a hard circle).
  const DRIVE = 1.35
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

/** Seconds to cross-fade the merge from the value shown at a state change to
 *  the new state's own merge — short enough to feel immediate, long enough that
 *  a branch switch never snaps the blob apart and reforms it. */
export const MERGE_XFADE = 0.4

/**
 * How merged the dots are (0 = ring, 1 = blob).
 *
 * Merge-into-a-puddle is RESERVED FOR SPEECH: only speaking/listening/idle track
 * the caller's speechMerge envelope. thinking and agents keep their steady merge
 * at 0 — the dots stay separate on the ring (thinking orbits them; agents pairs
 * them into pills) and never collapse into the speech blob. When `enterMerge` is
 * supplied (the merge shown at the instant this state was entered), the result
 * CROSS-FADES from it to the target over MERGE_XFADE, so a state change can never
 * discontinuously snap the merge — entering thinking from a held speech blob
 * dissolves the blob smoothly back to the orbiting ring. Without `enterMerge` the
 * steady per-state target is returned (deterministic harness/tests).
 *
 * This is the C6 fix: previously `mergeAmount` branch-switched formulas on a
 * state change, so e.g. speaking→thinking snapped merge in one frame.
 */
export function mergeAmount(
  state: OrbState,
  stateTime: number,
  speechMerge: number,
  enterMerge?: number
): number {
  const steady =
    state === 'thinking' || state === 'agents'
      ? 0
      : easeInOut(Math.min(1, Math.max(0, speechMerge)))
  if (enterMerge === undefined) return steady
  const w = easeInOut(Math.min(1, stateTime / MERGE_XFADE))
  return enterMerge * (1 - w) + steady * w
}

/** Entry-whirl shape. On entry to a whirling state the spin target OVERSHOOTS its
 *  cruise by `WHIRL_ADD` (scaled per preset), decaying with `WHIRL_TAU` so the
 *  ring visibly speeds up then eases to cruise over ~1s — the "fast then slow
 *  between states" effect. Deterministic (a function of stateTime, no random). */
export const WHIRL_ADD = 2.5
export const WHIRL_TAU = 0.35

/** Seconds the agents entry keeps the dots whirling on the ring BEFORE the pose
 *  (glide → pills) begins. Long enough to read as a fast orbit; the whirl spin
 *  overshoot has mostly decayed by the time the dots start settling. */
export const AGENTS_WHIRL = 1.0

/**
 * Target orbit-speed multiplier for a state at `stateTime` seconds in (1 = calm
 * idle cadence). Busy states spin the ring faster; the animator eases the LIVE
 * multiplier toward this so the change is never a jump (C9). Two shapes combine:
 *  - a steady CRUISE — thinking is busiest, speaking/listening get smaller
 *    bumps, idle/agents cruise at 1×;
 *  - an entry WHIRL — thinking and agents kick off with a decaying overshoot so
 *    the ring whirls fast on entry and eases down to cruise (speaking/listening
 *    don't whirl — they merge/rest).
 * Agents cruises at 1× (the pose is still), so its whole visible spin-up IS the
 * entry whirl, which plays before the dots settle into pills.
 */
export function spinTargetFor(
  state: OrbState,
  stateTime: number,
  params: OrbParams = DEFAULT_ORB_PARAMS
): number {
  const busy = params.spinBusyMult
  const cruise =
    state === 'thinking'
      ? busy
      : state === 'speaking'
        ? 1 + (busy - 1) * 0.45
        : state === 'listening'
          ? 1 + (busy - 1) * 0.15
          : 1 // idle, agents
  if (state !== 'thinking' && state !== 'agents') return cruise
  // Scale the whirl with the preset's spin budget (compact mounts stay calmer).
  const add = WHIRL_ADD * (busy / DEFAULT_ORB_PARAMS.spinBusyMult)
  return cruise + add * Math.exp(-Math.max(0, stateTime) / WHIRL_TAU)
}

/** Exponential time-constant (s) for easing the live spin multiplier toward its
 *  state target — a soft spin-up and a gentle decel into the settled state. */
export const SPIN_EASE_TAU = 0.18

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
  /** Merge value shown at the instant the current `state` was entered. When
   *  present, `mergeAmount` cross-fades from it so a state change never snaps
   *  the blob (C6). The app's OrbAnimator captures it on setState; deterministic
   *  renders omit it for the exact original per-state ramps. */
  enterMerge?: number
  /** Warped orbit clock (seconds). The app advances this by dt × the live spin
   *  multiplier so busy states rotate faster without an angle jump (C9); the
   *  noise/pulse still use the real `t`. Falls back to `t` when omitted. */
  orbitTime?: number
  /** Orbit cadence 0..1 (0 = step-then-rest, 1 = continuous glide). The app
   *  eases this across a state change for a smooth crossover; deterministic
   *  renders fall back to `orbitFlowFor(state)`. */
  flow?: number
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
  const merge = mergeAmount(state, stateTime, input.speechMerge ?? 0, input.enterMerge)
  const thinking = state === 'thinking'

  // Orbit runs on the (optionally speed-warped) orbit clock; everything else
  // (noise, pulse, agents timing) stays on real time. `flow` blends the ring
  // cadence from stepped (idle) to a continuous glide (busy) — thinking and the
  // agents entry whirl spin smoothly instead of stepping.
  const orbitT = input.orbitTime ?? t
  const flow = input.flow ?? orbitFlowFor(state)
  const angle = orbitAngle(orbitT, p, flow)

  // Merge travel is STAGGERED per dot (a rotational sweep: dots pool into the
  // puddle one after another and split back out the same way). A simultaneous
  // ring collapse left a punched hole at the center mid-merge (the smin union
  // of a ring is an annulus — skeptical-review Critical); staggering means
  // mass accumulates from the first arrivals, so the blob is solid throughout.
  // A WIDE stagger also spreads the gather/dissolve over a broad merge range so
  // the blob forms and breaks up dot-by-dot — never a one-frame ring↔blob cut.
  const STAGGER = 0.9
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
  // WHIRL-THEN-STAGE: for the first AGENTS_WHIRL seconds the dots stay on the
  // ring and orbit fast (the entry whirl — spin overshoots, flow glides), THEN
  // the pose plays. STAGED: the glide finishes BEFORE the stretch begins —
  // stretching while vertical neighbors were still in smooth-min range bridged
  // pills across rows into a two-row clump (review round 2). Dots glide as dots,
  // settle on their row centers, then lengthen into bars.
  const ap =
    state === 'agents' ? Math.min(1, Math.max(0, (stateTime - AGENTS_WHIRL) / 0.7)) : 0
  const agents = easeInOut(Math.min(1, ap / 0.6))
  const stretch = easeInOut(Math.max(0, (ap - 0.65) / 0.35))
  // Row assignment: each dot glides to the row matching its VERTICAL ORDER on
  // the ring when the pose begins (t - stateTime + AGENTS_WHIRL — deterministic).
  // Index-fixed pairing sent top-row dots straight through the second row's
  // dots, bridging pills mid-glide (review round 2).
  let rowOf: number[] | null = null
  if (ap > 0) {
    const a0 = orbitAngle(orbitT - stateTime + AGENTS_WHIRL, p, flow)
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
    dots.push({ x, y, r, halfLen, merge: mi })
  }

  // Center pool: grows as the first dots arrive and breathes so the held blob
  // feels liquid. It comes up EARLY in the merge (so it is already present and —
  // via the pool smin — bridged to the converging dots before they cluster; a
  // late pool left a standalone center blob = a phantom 9th dot, and left the
  // ring's interior unfilled = a punched hole). Its size is a SMOOTH, monotonic
  // function of merge (eased gate, no hard visibility floor, no mid-merge bump):
  // a floor or a hump made the rendered blob area jump in one frame as merge
  // swept past it during a dissolve (thinking→idle explode/reform — C6). The
  // shader ramps the pool's SMIN BRIDGE strength with merge to match, so the
  // pool grows and glues in gradually instead of snapping onto the dots. The
  // speech pool swells slightly with the (bounded) voice; thinking breathes
  // quicker.
  const poolGate = easeInOut(Math.min(1, Math.max(0, (merge - 0.3) / 0.42)))
  const poolBase = thinking ? 0.34 : 0.42 * (0.92 + 0.14 * shaped)
  const poolPulse = thinking ? 0.13 * Math.sin(t * 4.6) : (0.07 + 0.05 * shaped) * Math.sin(t * 1.7)
  const centerR = poolGate * p.orbitRadius * poolBase * (1 + poolPulse)

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
