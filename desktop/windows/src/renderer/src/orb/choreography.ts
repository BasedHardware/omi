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
// States (amended per Chris 2026-07-11: the speech blob is REPLACED by a
// scrolling amplitude-history WAVEFORM — see waveform.ts. Audio-active states
// line the 8 ring dots up into a horizontal row, then hand off to the bar
// visualizer; a silent sample is a dot, so the resting waveform IS the dots):
//   idle       — slow orbit with ease-in-out steps (rotate → rest → resume).
//   listening  — quiet listening: same calm orbit (the mic is open, nothing is
//                being said). With a live speech signal (speechMerge > 0) it
//                becomes the waveform (recording the user's voice).
//   speaking   — the spoken TTS reply: the ring dots glide into a horizontal
//                line (staggered, like the agents pose) and hand off to the
//                waveform row, whose bar heights track the live reply amplitude
//                (bounded). Dissolves back to the ring when speech ends (the
//                caller eases `speechMerge` down via stepMergeEnvelope).
//   thinking   — the dots STAY SEPARATE on the ring and orbit CONTINUOUSLY at an
//                elevated speed. Entry kicks off a fast whirl that eases down to
//                a steady cruise. Also covers transcribing and a streaming reply.
//   agents     — entry whirls the ring fast for ~1s, THEN the dots pair up into
//                four status pills (clean, understated) while the agent runs.
//
// Genesis (summon): scale 0 → full disc with an ease-out spring (slight
// overshoot, fast settle) — never a fade/slide of a full-size element.
// Morph: disc → rounded-rect is a single interpolation parameter consumed by
// the SDF shader (one shape, continuous).

import { waveBars, waveHalfWidth, slotCountForAspect, type WaveBar } from './waveform'

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
  // Bumped 0.095 → 0.1 (user: "a very tiny bit thicker", ~5%). Because the
  // waveform's resting dot is pinned to RING_DOT_RENDER_RADIUS (below), this
  // thickens the ring dots AND the resting waveform dots together — one knob.
  dotRadius: 0.1,
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

/**
 * The rendered radius of an orbiting ring dot, in the shader's normalized
 * short-axis units (the shader scales each dot by `u_disc`, so the on-screen
 * radius is `dotRadius × discRadius` — see orbRenderer/shader). Exported as the
 * SINGLE SOURCE OF TRUTH so the waveform's resting dot (waveform.ts `waveBars`)
 * can render at the SAME size: the ring↔waveform crossfade then swaps a ring dot
 * for a resting bar-dot of identical radius, with no thickness pop (the two used
 * to differ ~45% in area). Derived from the DEFAULT params — the main orb that
 * performs the crossfade uses them; compact/notch presets size their own ring
 * dots but the waveform row is always the default's.
 */
export const RING_DOT_RENDER_RADIUS = DEFAULT_ORB_PARAMS.dotRadius * DEFAULT_ORB_PARAMS.discRadius

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
    // Thinking cruise must be UNMISTAKABLY fast at 22–26px — a user glancing at
    // the bar pill has to notice the ring is spinning. 1.55 read as barely
    // turning (user + investigator); match the default 2.0× busy cruise. The
    // whirl overshoot scales with this, so the entry spins up hard then settles
    // to a clearly-quick steady orbit.
    spinBusyMult: 2.0
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
  /** Roll-up progress 0..1 (the lower staging band, see AUDIO_STAGE_SPLIT): 0 =
   *  idle ring (dark disc + orbiting dots), 1 = the dots have fanned out onto the
   *  flat line. The shader fades the dark DISC out as this rises while the DOTS
   *  travel at full opacity — the ring visibly unrolls into the line instead of a
   *  ring↔line opacity crossfade. Saturates before the bar handoff begins, so on
   *  exit the bars are gone before this starts falling (a true mirror of entry). */
  waveMix: number
  /** Dot→bar handoff 0..1, staged AFTER the unroll (0 through the line-up, ramps
   *  once the row is formed). ON the line the white dots crossfade to the bar
   *  primitives (a representation swap at the same positions — never a position
   *  crossfade). 0 keeps the traveling/rested dots; 1 shows only the bars. */
  barMix: number
  /** Vertical bars for the waveform (normalized short-axis units, centered on
   *  y=0). Empty when waveMix is 0. */
  waveBars: WaveBar[]
  /** Global horizontal translation of the whole rendered pose (short-axis units;
   *  the shader shifts `q.x` by it, moving disc + dots + pool together). 0 in
   *  steady operation; the fail tremor (failTremorOffset) drives it briefly. */
  poseOffsetX: number
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
 * How merged the dots are into the legacy puddle blob (0 = ring, 1 = blob).
 *
 * The speech blob is RETIRED — audio states now render the waveform (see
 * computeOrbFrame / waveform.ts), so no state merges into a puddle: the steady
 * target is 0 everywhere. The signature is kept (the animator/harness still track
 * it) so a residual blob from any prior frame dissolves cleanly: when `enterMerge`
 * is supplied it CROSS-FADES from it down to 0 over MERGE_XFADE rather than
 * snapping. In steady operation this is uniformly 0.
 */
export function mergeAmount(
  _state: OrbState,
  stateTime: number,
  _speechMerge: number,
  enterMerge?: number
): number {
  if (enterMerge === undefined) return 0
  const w = easeInOut(Math.min(1, stateTime / MERGE_XFADE))
  return enterMerge * (1 - w)
}

/**
 * Waveform crossfade 0..1 (0 = ring dots, 1 = full bar visualizer), driven by the
 * speech-merge envelope. The app opens the gate (speechMerge → 1) only on audio
 * states — 'speaking', or 'listening' with a live speech signal — and closes it
 * on any other; the SAME envelope that used to drive the blob now drives the ring
 * → waveform handoff. Following the envelope (not the raw state) is what makes a
 * state change mid-utterance — e.g. speaking → thinking on release — DISSOLVE the
 * bars back to the ring over the release instead of snapping them off the instant
 * the state flips. Eased for a smooth glide.
 */
export function waveMixFor(_state: OrbState, speechMerge: number): number {
  return easeInOut(Math.min(1, Math.max(0, speechMerge)))
}

/**
 * Audio-staging split. The waveform entrance/exit is TWO stages of the single
 * speech-merge envelope, and they must never overlap or the exit reads as a
 * bars↔ring CROSSFADE (the dark disc + orbiting dots fade in WHILE the bars fade
 * out) instead of a roll-up. So the envelope is split into two DISJOINT bands:
 *   • lower band [0, SPLIT] — the dots' roll-up (ring ↔ flat line) and the disc
 *     fade. Owns `unrollProgressFor`.
 *   • upper band [SPLIT, 1] — the dot ↔ bar handoff (bars fade in/out ON the
 *     already-formed line). Owns `barResponseFor`.
 * Because the bands don't overlap, ENTRY (roll out over the lower band, THEN bars
 * over the upper) and EXIT (envelope runs the other way: bars fade over the upper
 * band, THEN the dots roll up over the lower) are exact time-reverses — a true
 * mirror. And because BOTH are pure functions of the one envelope, every driver
 * that steps that envelope (the app's OrbAnimator, the deterministic harness)
 * reproduces the identical staging: there is no separately-stepped bar gain to
 * forget to mirror (the class of bug where the harness disagreed with live).
 */
export const AUDIO_STAGE_SPLIT = 0.55

/** Roll-up progress 0..1 from the eased audio envelope (see `waveMixFor`): 0 =
 *  idle ring, 1 = dots fanned onto the flat line. Reaches 1 by AUDIO_STAGE_SPLIT
 *  so the whole upper band is free for the bar handoff (dots held on the line). */
export function unrollProgressFor(audioMix: number): number {
  return Math.min(1, Math.max(0, audioMix) / AUDIO_STAGE_SPLIT)
}

/** Dot→bar handoff gain 0..1 from the eased audio envelope: pinned at 0 through
 *  the whole roll-up (lower band) so the traveling dots are never crossfaded, then
 *  eased 0→1 across the UPPER band (dots already on the line). eased at both ends
 *  for a gentle fade. This REPLACES the animator's old separately-stepped
 *  `waveResponse`; callers may still pass an explicit `waveResponse` to override
 *  it (the isolation checks pin it to 0). */
export function barResponseFor(audioMix: number): number {
  return easeInOut((Math.min(1, Math.max(0, audioMix)) - AUDIO_STAGE_SPLIT) / (1 - AUDIO_STAGE_SPLIT))
}

/** Per-dot stagger for the unroll (0 = all dots straighten together, 1 = fully
 *  sequential fan-out). A moderate value reads as the ring PEELING open from one
 *  end into the line rather than squashing flat all at once. */
export const UNROLL_STAGGER = 0.55
/** Peak height (disc units) of the transient arc the row bows through mid-unroll,
 *  so it reads as "circle → open arc → flat line" instead of a straight collapse.
 *  Zero at both endpoints (an exact ring at u=0, an exact flat line at u=1). */
export const UNROLL_ARC = 0.34

/** One point of the unrolled ring. */
export type UnrollPoint = { x: number; y: number }

/**
 * UNROLL / FAN-OUT: the ring peels open into a horizontal line (user's ask —
 * "the dots UNROLL and FAN OUT to make a line"). Pure and deterministic.
 *
 * At `u`=0 every dot sits EXACTLY on the live ring (`orbitRadius` at `angle`); at
 * `u`=1 the dots are an evenly spaced horizontal row (y=0) spanning ±`lineHalf`,
 * ordered left→right by their ring x so paths never cross. In between: each dot's
 * straighten progress is STAGGERED by its rank (the row lays down from one end),
 * and the whole row bows through a transient arc (UNROLL_ARC, zero at both ends)
 * so it reads as a circle opening into an arc and flattening — not a squash. Feed
 * the reverse (u: 1→0) for the exit (the line rolls back up into the ring).
 */
export function unrollPositions(
  u: number,
  angle: number,
  lineHalf: number,
  p: OrbParams = DEFAULT_ORB_PARAMS
): UnrollPoint[] {
  const uc = Math.min(1, Math.max(0, u))
  const R = p.orbitRadius
  // Rank the dots by their current ring x (leftmost → slot 0) so the fan-out is
  // monotone in x and the paths don't cross.
  const order = Array.from({ length: DOT_COUNT }, (_, i) => i).sort(
    (A, B) =>
      Math.cos(angle + (A * 2 * Math.PI) / DOT_COUNT) -
      Math.cos(angle + (B * 2 * Math.PI) / DOT_COUNT)
  )
  const rankOf = new Array<number>(DOT_COUNT)
  order.forEach((dotIdx, rank) => {
    rankOf[dotIdx] = rank
  })
  // Transient arc envelope: 0 at u=0 and u=1, a single hump between.
  const arcEnv = Math.sin(Math.PI * uc)
  const out: UnrollPoint[] = []
  for (let i = 0; i < DOT_COUNT; i++) {
    const a = angle + (i * 2 * Math.PI) / DOT_COUNT
    const ringX = Math.cos(a) * R
    const ringY = Math.sin(a) * R
    const rank = rankOf[i]
    const centered = (rank + 0.5) / DOT_COUNT - 0.5 // -0.5..0.5
    const lineX = centered * 2 * lineHalf
    // Staggered per-dot straighten (the fan-out lays down from the left end).
    const s = UNROLL_STAGGER
    const ui = Math.min(1, Math.max(0, uc * (1 + s) - s * (rank / (DOT_COUNT - 1))))
    const ue = easeInOut(ui)
    const x = ringX * (1 - ue) + lineX * ue
    // Bow the row through an arc: dots near the center rise most (cos peaks at the
    // middle rank), the ends stay put; the whole thing vanishes at both endpoints.
    const bow = arcEnv * UNROLL_ARC * Math.cos(centered * Math.PI)
    const y = ringY * (1 - ue) + 0 * ue - bow
    out.push({ x, y })
  }
  return out
}

// The bar handoff used to be a separately-stepped gain (WAVE_RESPONSE_ATTACK /
// _RELEASE / _GATE) that the animator eased and the harness had to mirror by hand
// — the source of the exit crossfade (release began too late and overlapped the
// roll-up) and of the harness disagreeing with live. It is now the deterministic
// UPPER staging band, barResponseFor / AUDIO_STAGE_SPLIT (above).

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
 *  - a steady CRUISE — thinking and speaking cruise at the FULL busy multiplier
 *    (speaking was 1.45× but the user "never perceived the speed-up" during voice
 *    interactions, which map to 'speaking' — so it now matches thinking's 2×);
 *    listening gets a smaller bump; idle/agents cruise at 1×. The cruise carries
 *    NO time dependence, so a settled state has a perfectly CONSTANT spin rate —
 *    every speed change is an eased transition ramp (or the entry whirl below),
 *    never a within-state pulse.
 *  - an entry WHIRL — thinking and agents kick off with a decaying overshoot so
 *    the ring whirls fast on entry and eases down to cruise. This flourish stays
 *    EXCLUSIVE to thinking/agents; speaking/listening are steady from entry (they
 *    roll into the waveform / rest, so a whirl would fight that transition).
 * Agents cruises at 1× (the pose is still), so its whole visible spin-up IS the
 * entry whirl, which plays before the dots settle into pills.
 */
export function spinTargetFor(
  state: OrbState,
  stateTime: number,
  params: OrbParams = DEFAULT_ORB_PARAMS,
  // Clock for the entry-WHIRL decay, separate from `stateTime`. The whirl must
  // land on the VISIBLE ring: entering 'thinking' from 'speaking', the orb is
  // still the waveform line rolling back up (~0.85s), so anchoring the whirl to
  // state entry decays it to ~9% before the ring even reappears (the user never
  // sees the ring speed up). The animator passes the time since the ring RE-FORMED
  // (waveMix < WHIRL_ANCHOR_EPS) instead; deterministic callers default it to
  // `stateTime` (unchanged when a whirl state is entered from a non-audio state,
  // where the ring is already present).
  whirlTime: number = stateTime
): number {
  const busy = params.spinBusyMult
  const cruise =
    state === 'thinking' || state === 'speaking'
      ? busy
      : state === 'listening'
        ? 1 + (busy - 1) * 0.15
        : 1 // idle, agents
  if (state !== 'thinking' && state !== 'agents') return cruise
  // Scale the whirl with the preset's spin budget (compact mounts stay calmer).
  const add = WHIRL_ADD * (busy / DEFAULT_ORB_PARAMS.spinBusyMult)
  return cruise + add * Math.exp(-Math.max(0, whirlTime) / WHIRL_TAU)
}

/** waveMix at/under which the ring is considered RE-FORMED, so the entry whirl's
 *  decay clock may start (see spinTargetFor / anchorWhirlStart). Small but not 0
 *  so the whirl fires as the roll-up finishes, not a frame late. */
export const WHIRL_ANCHOR_EPS = 0.05

/**
 * Anchor the entry-whirl decay clock to the moment the ring RE-FORMS. Pure
 * reducer over the animator's per-frame state: returns the time the whirl should
 * count from (or `null` = "not yet — hold the whirl primed at full overshoot").
 * While a whirling state is entered but the waveform line is still rolling back
 * (waveMix ≥ eps), stays `null`; the first frame the ring is formed (waveMix <
 * eps) it latches the current time; once latched it holds (a single decay per
 * episode). Non-whirl states clear it. The animator resets it to `null` on every
 * setState so each entry re-anchors.
 */
export function anchorWhirlStart(
  prev: number | null,
  isWhirlState: boolean,
  t: number,
  waveMix: number
): number | null {
  if (!isWhirlState) return null
  if (prev !== null) return prev
  return waveMix < WHIRL_ANCHOR_EPS ? t : null
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

// --- Fail gesture ------------------------------------------------------------

/**
 * "Failed voice turn" gesture: a brief, understated damped horizontal TREMOR of
 * the WHOLE orb — it shakes side-to-side (a subtle "no") with decaying amplitude,
 * then settles to idle. MOTION ONLY — no color change, no purple. A deterministic
 * tween, never a live sim: a pure function of the injected time and the stamped
 * `failedAt`, so it is scrubbable and reproduces identically in the app and the
 * harness. It drives OrbFrame.poseOffsetX (→ shader u_poseOffset), a GLOBAL
 * horizontal translation of the rendered pose, so the dark disc AND the dots
 * shake together (offsetting only the dots would slide them inside a stationary
 * disc — not an orb shake).
 *
 * Tunable feel (dialed against real frames — the orchestrator's knobs):
 *   FAIL_GESTURE_MS           — total duration, milliseconds.
 *   FAIL_GESTURE_AMPLITUDE    — start amplitude as a fraction of the orb radius.
 *   FAIL_GESTURE_OSCILLATIONS — number of full side-to-side swings.
 */
export const FAIL_GESTURE_MS = 500
export const FAIL_GESTURE_AMPLITUDE = 0.06
export const FAIL_GESTURE_OSCILLATIONS = 2

/**
 * Horizontal pose offset (short-axis normalized units — the same space the shader
 * shifts `q` by, and consistent with the dots once scaled by the disc radius) for
 * the fail tremor at absolute time `t`, given the time the gesture was stamped
 * (`failedAt`; omit / non-finite = no gesture). EXACTLY 0 at u=0 and at u>=1 (both
 * the sine and the decay envelope vanish there), so it neither pops in nor leaves
 * a residual lean. The amplitude decays across the gesture via (1 - easeInOut(u)),
 * so the first swing is the largest and each later peak is smaller.
 */
export function failTremorOffset(
  t: number,
  failedAt: number | undefined,
  p: OrbParams = DEFAULT_ORB_PARAMS
): number {
  if (failedAt === undefined || !Number.isFinite(failedAt)) return 0
  const durS = Math.max(1e-6, FAIL_GESTURE_MS / 1000)
  const u = Math.min(1, Math.max(0, (t - failedAt) / durS))
  if (u <= 0 || u >= 1) return 0
  const swing = Math.sin(2 * Math.PI * FAIL_GESTURE_OSCILLATIONS * u)
  const decay = 1 - easeInOut(u)
  return FAIL_GESTURE_AMPLITUDE * p.discRadius * swing * decay
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
  /** Absolute animation time (same clock as `t`) at which the fail tremor was
   *  stamped; omit / non-finite when no fail gesture is playing. Drives the
   *  deterministic horizontal shake (failTremorOffset → poseOffsetX). */
  failedAt?: number
  /** Disc → rounded-rect morph 0..1 (expanded surface drives this). */
  morph?: number
  /** Per-slot loudness history 0..1 (oldest→newest = left→right) for the
   *  waveform. The animator supplies its smoothed ring-buffer window; the harness
   *  scripts it. When omitted on an audio state the row rests as silence dots. */
  waveLevels?: number[]
  /** Canvas aspect (width / height). Lays out the bar row and the dots' glide
   *  line so a wide mount gets more slots than a square one. Defaults to 1. */
  aspect?: number
  /** Bar-response gain 0..1 OVERRIDE. Normally omitted — the handoff is derived
   *  from the envelope's upper staging band (barResponseFor), so the app and the
   *  harness agree. Supply it only to isolate the dots (the checks pin it to 0 so
   *  no bars render) or to force a specific gain in a static frame. */
  waveResponse?: number
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

  // Waveform crossfade: on an audio state the speech-merge envelope glides the
  // ring dots into a horizontal line and hands off to the bar visualizer. 0 on
  // every non-audio state (idle/thinking/agents keep their ring/pose untouched).
  // The one envelope is split into two DISJOINT stages (see AUDIO_STAGE_SPLIT):
  // `unrollU` (the roll-up, lower band) drives the dot travel + disc fade, and the
  // bar handoff (upper band) rides on top only once the dots are on the line — so
  // entry and exit are exact mirrors and the exit never crossfades bars↔ring.
  const aspect = input.aspect ?? 1
  const audioMix = waveMixFor(state, input.speechMerge ?? 0)
  const unrollU = unrollProgressFor(audioMix)
  const audioGlide = unrollU > 0
  // Dot glide line half-width (disc units), clamped so the edge dots never leave
  // the unit disc even as they line up (they fade out as the bars take over).
  const lineHalf = Math.min(waveHalfWidth(aspect) / p.discRadius, 0.88)

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
  const ap = state === 'agents' ? Math.min(1, Math.max(0, (stateTime - AGENTS_WHIRL) / 0.7)) : 0
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

  // Waveform UNROLL: the ring peels open into the horizontal row as waveMix→1 —
  // staggered per-dot fan-out through a transient arc (see unrollPositions), the
  // exact ring at 0 and the exact line at 1. The dots fade out with the ring layer
  // as the bar visualizer fades in. Mutually exclusive with the agents pose (audio
  // states ≠ agents). Computed once per frame from the live orbit angle.
  const unroll = audioGlide ? unrollPositions(unrollU, angle, lineHalf, p) : null

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
    } else if (unroll) {
      x = unroll[i].x
      y = unroll[i].y
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

  // Waveform bars: the scrolling amplitude-history row (empty unless the audio
  // crossfade is engaged). Slot count follows the aspect when no explicit levels
  // are supplied. The RESPONSE gain (1 by default; the animator ramps it in after
  // the unroll) scales every level, so during the line-up the row is flat dots and
  // the bars only come alive once the row is formed — and flatten before the exit.
  // Bar-response gain: the UPPER-band handoff (barResponseFor) — 0 through the
  // whole roll-up, easing in only once the dots are on the line. A caller may
  // override it (the isolation checks pin it to 0 to render only the traveling
  // dots); by default it is derived from the same envelope, so the app and the
  // harness stage the bars identically with nothing separately stepped.
  const response = Math.min(1, Math.max(0, input.waveResponse ?? barResponseFor(audioMix)))
  let bars: WaveBar[] = []
  if (unrollU > 0) {
    const slotCount = input.waveLevels?.length ?? slotCountForAspect(aspect)
    const raw = input.waveLevels ?? new Array<number>(slotCount).fill(0)
    const levels = response === 1 ? raw : raw.map((l) => l * response)
    bars = waveBars(levels, aspect)
  }
  // Dot→bar handoff: barResponse rides on the roll-up (unrollU), so it is 0 while
  // the dots travel (they stay fully visible — never a ring↔line opacity crossfade)
  // and rises only once the row is formed. On exit the reverse: bars fade off the
  // line FIRST, then the dots roll up at full opacity. 0 on the ring (unrollU 0).
  const barMix = unrollU * response

  return {
    dots,
    merge,
    centerR,
    waveAmp,
    amplitude: shaped,
    morph: Math.min(1, Math.max(0, input.morph ?? 0)),
    genesis: genesisTime === Infinity ? 1 : genesisScale(genesisTime, p),
    noiseTime: t,
    waveMix: unrollU,
    barMix,
    waveBars: bars,
    // Deterministic fail tremor: a global horizontal shake of the whole pose
    // (0 unless a fail gesture is mid-play — pure function of t and failedAt).
    poseOffsetX: failTremorOffset(t, input.failedAt, p),
    params: p
  }
}
