/**
 * The animated Omi mark, ported from the Flutter app's `omi_orb_motion.dart`.
 *
 * Every motion is a closed-form function of the lap position, so any two of
 * them can be blended by interpolating their output — that is what lets the
 * mark change its mind mid-cycle without snapping.
 */

export interface OmiVec {
  x: number;
  y: number;
}

const TAU = Math.PI * 2;

/**
 * A cubic Bezier easing solver matching Flutter's `Cubic`. The curve's control
 * points are (a, b) and (c, d); x is solved for t by Newton-Raphson, falling
 * back to bisection when the derivative is too flat to trust.
 */
export class CubicEasing {
  constructor(
    private readonly a: number,
    private readonly b: number,
    private readonly c: number,
    private readonly d: number,
  ) {}

  private static value(p1: number, p2: number, t: number): number {
    const inv = 1 - t;
    return 3 * inv * inv * t * p1 + 3 * inv * t * t * p2 + t * t * t;
  }

  private static slope(p1: number, p2: number, t: number): number {
    const inv = 1 - t;
    return 3 * inv * inv * p1 + 6 * inv * t * (p2 - p1) + 3 * t * t * (1 - p2);
  }

  transform(x: number): number {
    if (x <= 0) return 0;
    if (x >= 1) return 1;

    // Newton-Raphson first: it converges in a handful of steps wherever the
    // curve is not close to horizontal.
    let t = x;
    for (let i = 0; i < 8; i++) {
      const error = CubicEasing.value(this.a, this.c, t) - x;
      if (Math.abs(error) < 1e-9) return CubicEasing.value(this.b, this.d, t);
      const slope = CubicEasing.slope(this.a, this.c, t);
      if (Math.abs(slope) < 1e-9) break;
      t -= error / slope;
    }

    // Bisection fallback: slower, but it cannot diverge, so a flat or
    // overshooting segment still resolves.
    let low = 0;
    let high = 1;
    t = x;
    for (let i = 0; i < 64; i++) {
      const value = CubicEasing.value(this.a, this.c, t);
      if (Math.abs(value - x) < 1e-9) break;
      if (value > x) high = t;
      else low = t;
      t = (low + high) / 2;
    }
    return CubicEasing.value(this.b, this.d, t);
  }
}

/** Flutter's `Curves.easeInCubic`. */
export const easeInCubic = new CubicEasing(0.55, 0.055, 0.675, 0.19);
/** Flutter's `Curves.easeOutBack` — it overshoots past 1 on purpose. */
export const easeOutBack = new CubicEasing(0.175, 0.885, 0.32, 1.275);
/** Flutter's `Curves.easeOutCubic`. */
export const easeOutCubic = new CubicEasing(0.215, 0.61, 0.355, 1);

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

export function smoothOmiLevel(
  current: number,
  target: number,
  elapsedMs: number,
): number {
  const from = clamp01(current);
  const to = clamp01(target);
  const rate = to > from ? 14 : 7;
  const duration = Math.max(0, Math.min(64, elapsedMs));
  return from + (to - from) * (1 - Math.exp((-rate * duration) / 1000));
}

/**
 * The geometry of the Omi mark, measured from `assets/images/omi_logo.png`
 * and kept identical to `assets/images/omi_mark.svg`, the source of truth.
 *
 * The artwork is 260x260 with the ring centred at (129.5, 129.5) and every
 * dot 17.2 units across the radius. The four dots on the axes sit at radius
 * 86.71 and the four on the diagonals at 91.92 — the mark is a rounded
 * square rather than a true circle, and that is deliberate, so it is kept.
 *
 * Dot order matches the SVG: index 0 is due north, and the rest run
 * clockwise (0 = 12 o'clock, 1 = 1:30, 2 = 3 o'clock … 7 = 10:30).
 */
export const OmiMarkGeometry = {
  canvas: 260,
  centre: 129.5,
  dotRadius: 17.2,
  axisRadius: 86.71,
  diagonalRadius: 91.92,
  dotCount: 8,

  /** Distance from the centre to dot `i` in canvas units. */
  radiusOf(i: number): number {
    return i % 2 === 0 ? OmiMarkGeometry.axisRadius : OmiMarkGeometry.diagonalRadius;
  },

  /** The angle of dot `i`, measured clockwise from due north. */
  angleOf(i: number): number {
    return (i * Math.PI) / 4;
  },

  /**
   * The unit vector pointing at `angle`, clockwise from due north. Canvas y
   * grows downward, so north is -y.
   */
  directionAt(angle: number): OmiVec {
    return { x: Math.sin(angle), y: -Math.cos(angle) };
  },

  /** Where dot `i` sits at rest, measured from the ring centre. */
  restOf(i: number): OmiVec {
    return scale(
      OmiMarkGeometry.directionAt(OmiMarkGeometry.angleOf(i)),
      OmiMarkGeometry.radiusOf(i),
    );
  },

  /**
   * Dot `i`'s position in the wave chain, left to right.
   *
   * The ring is cut between due south and its south-west neighbour and
   * unrolled clockwise, so lane order is SW, W, NW, N, NE, E, SE, S. Because
   * the chain follows ring order, a phase that runs along the lanes is the
   * same phase running around the ring: a travelling wave stays a travelling
   * wave through the morph rather than scrambling into it.
   */
  laneOf(i: number): number {
    return (i + 3) % OmiMarkGeometry.dotCount;
  },

  /** Half the width the wave layouts spread across, in canvas units. */
  laneSpan: 92,

  /**
   * Dots shrink to this on the chain. Eight dots at full size across the span
   * overlap by more than half their width and the wave reads as one blob;
   * this is the largest they can be and still leave daylight between them.
   */
  laneDotScale: 0.68,

  /** The x of dot `i`'s lane, measured from the ring centre. */
  laneXOf(i: number): number {
    return (
      (OmiMarkGeometry.laneOf(i) / (OmiMarkGeometry.dotCount - 1) - 0.5) *
      2 *
      OmiMarkGeometry.laneSpan
    );
  },

  /**
   * The resting y of dot `i`'s lane. A shallow arc rather than a dead flat
   * rule, so the flattened chain keeps a memory of the ring it came from.
   */
  laneYOf(i: number): number {
    const t = OmiMarkGeometry.laneXOf(i) / OmiMarkGeometry.laneSpan;
    return 7 * t * t - 2;
  },
} as const;

function scale(v: OmiVec, k: number): OmiVec {
  return { x: v.x * k, y: v.y * k };
}

function add(a: OmiVec, b: OmiVec): OmiVec {
  return { x: a.x + b.x, y: a.y + b.y };
}

function lerpVec(a: OmiVec, b: OmiVec, t: number): OmiVec {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

/**
 * What the mark is doing. The geometry never changes — only how the eight
 * dots move — so the identity carries every state instead of being swapped
 * out for a spinner, a waveform and a checkmark.
 *
 * - `idle`: at rest — a slow orbit and a barely-there breath.
 * - `loading`: waiting on something that has not started returning yet.
 * - `thinking`: working out what to say.
 * - `searching`: looking something up outside itself.
 * - `streaming`: a reply is arriving, token by token.
 * - `speaking`: talking back.
 * - `listening`: hearing you. The only state that reads the input level, and
 *   the only one that becomes a wave — a waveform anywhere else is a level
 *   meter with nothing to meter.
 * - `success`: done — the dots scatter outward once and re-form.
 */
export type OmiOrbState =
  | 'idle'
  | 'loading'
  | 'thinking'
  | 'searching'
  | 'streaming'
  | 'speaking'
  | 'listening'
  | 'success';

/**
 * One choreography the eight dots can perform.
 *
 * - `mark`: brand rest — the ring, a slow orbit and a shared breath.
 * - `spin`: the bare orbit, no breath — the original idle, kept as a fallback.
 * - `pulse`: the site thinking pulse — a highlight walking a stationary ring.
 * - `gather`: the dots fall inward into a knot and spring back out past rest.
 * - `sine`: the ring flattens into a chain carrying a travelling sine, the
 *   amplitude and the depth of the flattening both driven by the input level.
 * - `travellingWave`: a packet of energy visibly runs along the chain, left to
 *   right.
 * - `standingWave`: neighbours in antiphase — the nodes hold still, the
 *   antinodes breathe.
 * - `pendulumWave`: eight periods, one apart, so the chain runs sine ->
 *   travelling -> chaos -> line -> back over a single lap.
 * - `tusiPendulum`: the pendulum wave run along Tusi diameters instead of
 *   lanes: each dot slides through the centre on its own line at its own rate,
 *   so the ring blooms into a turning lattice and reassembles itself at the
 *   lap mark.
 * - `audioBars`: beads riding the tops of eight level bars.
 * - `tusi`: the Tusi couple — a circle rolling inside a circle at twice the
 *   rate, so every dot's path is a straight diameter. The circle drawing a
 *   line.
 * - `nestedOrbit`: a smaller circle rolls around the inside of the mark, dots
 *   riding its rim.
 * - `doubleCircle`: the four axis dots hold the mark while the four diagonals
 *   collapse onto a tighter concentric ring and counter-rotate.
 * - `epicycloid`: a small circle rolls around the outside, one dot leading and
 *   the rest trailing it.
 * - `lissajous`: x and y sines at a 2:3 ratio, kept inside the mark's bounds.
 * - `pendulumSwing`: the whole mark hangs and swings, the dots dragging behind
 *   the swing.
 * - `successBurst`: the one-shot scatter and re-form.
 */
export type OmiOrbMotion =
  | 'mark'
  | 'spin'
  | 'pulse'
  | 'gather'
  | 'sine'
  | 'travellingWave'
  | 'standingWave'
  | 'pendulumWave'
  | 'tusiPendulum'
  | 'audioBars'
  | 'tusi'
  | 'nestedOrbit'
  | 'doubleCircle'
  | 'epicycloid'
  | 'lissajous'
  | 'pendulumSwing'
  | 'successBurst';

/**
 * Where dot `i` sits this frame, measured from the ring centre in the mark's
 * 260-unit canvas space. Renderers scale it; tests read it directly.
 */
export interface OmiDotPlacement {
  /** Displacement from the ring centre, in canvas units. */
  offset: OmiVec;
  /** Multiplies `OmiMarkGeometry.dotRadius`. */
  scale: number;
  alpha: number;
}

export function omiDotPlacementLerp(
  a: OmiDotPlacement,
  b: OmiDotPlacement,
  t: number,
): OmiDotPlacement {
  return {
    offset: lerpVec(a.offset, b.offset, t),
    scale: a.scale + (b.scale - a.scale) * t,
    alpha: a.alpha + (b.alpha - a.alpha) * t,
  };
}

/**
 * The site thinking pulse: `@keyframes omi-dot-pulse` in `site/web/styles.css`.
 * Each dot peaks at 12% of its cycle, holds dim until 70%, then rests —
 * staggered by one eighth so the highlight reads as a single point of light
 * walking the ring.
 */
export const OmiThinkingPulse = {
  ease: new CubicEasing(0.22, 1, 0.36, 1),
  baseOpacity: 0.62,
  peakOpacity: 1.0,
  baseScale: 1.0,
  peakScale: 1.14,
  peakAt: 0.12,
  holdUntil: 0.7,

  /** Local phase for dot `i` within the current lap, 0 to 1. */
  localPhase(i: number, turn: number): number {
    const raw = (turn + (OmiMarkGeometry.dotCount - i) / OmiMarkGeometry.dotCount) % 1;
    return raw < 0 ? raw + 1 : raw;
  },

  /** Opacity and scale at `localT`, matching the site keyframes. */
  at(localT: number): { opacity: number; scale: number } {
    const p = OmiThinkingPulse;
    if (localT <= p.peakAt) {
      const t = p.ease.transform(localT / p.peakAt);
      return {
        opacity: p.baseOpacity + (p.peakOpacity - p.baseOpacity) * t,
        scale: p.baseScale + (p.peakScale - p.baseScale) * t,
      };
    }
    if (localT <= p.holdUntil) {
      const t = p.ease.transform((localT - p.peakAt) / (p.holdUntil - p.peakAt));
      return {
        opacity: p.peakOpacity + (p.baseOpacity - p.peakOpacity) * t,
        scale: p.peakScale + (p.baseScale - p.peakScale) * t,
      };
    }
    return { opacity: p.baseOpacity, scale: p.baseScale };
  },
};

/**
 * The motions a state may be expressed by.
 *
 * Several states offer more than one so the mark does not play the identical
 * clip every time it waits — but the choices within a state read the same at a
 * glance, so the animation still says what the app is doing. Variety within a
 * meaning, not variety instead of one.
 *
 * `listening` is deliberately alone: the wave is the input level made visible,
 * and using it for anything else would be a meter with nothing to meter.
 */
export const omiMotionsForState: Record<OmiOrbState, readonly OmiOrbMotion[]> = {
  idle: ['mark'],
  // Waiting: something turns, nothing is claimed about progress.
  loading: ['pulse', 'doubleCircle', 'nestedOrbit'],
  // Working: inward, gathered, self-contained.
  thinking: ['gather', 'tusi', 'standingWave'],
  // Reaching outward for something.
  searching: ['epicycloid', 'lissajous', 'nestedOrbit'],
  // Arriving: energy travelling along the chain, one direction.
  streaming: ['travellingWave'],
  // Talking: a mouth, not an ear — bars rather than a level wave.
  speaking: ['audioBars'],
  listening: ['sine'],
  success: ['successBurst'],
};

/**
 * The choreography `state` performs unless a caller names a motion outright.
 *
 * `seed` picks among the candidates. Callers pass something stable for the
 * life of one wait — a message id, a request counter — so the motion is
 * varied between waits and steady during one. A changing seed mid-wait would
 * make the mark twitch between motions, which is worse than never varying.
 */
export function omiMotionForState(state: OmiOrbState, seed = 0): OmiOrbMotion {
  const candidates = omiMotionsForState[state] ?? (['mark'] as const);
  return candidates[Math.abs(seed) % candidates.length] as OmiOrbMotion;
}

/**
 * Travels `sine` makes across the chain per lap, and the phase one lane lags
 * the one before it. Whole travels per lap is what lets the clock restart
 * without the wave snapping.
 */
export const omiSineTravelsPerLap = 2;
export const omiSineLanePhase = 0.1875;

/**
 * Swings the slowest lane makes per lap of `pendulumWave`; the fastest makes
 * seven more.
 */
const pendulumBase = 9;

/** Slides the slowest diameter makes per lap of `tusiPendulum`. */
const tusiPendulumBase = 5;

/**
 * The whole-lap swing counts, exposed so a test can assert they stay integers
 * — the moment one is not, the motion stops resynchronising.
 */
export const omiPendulumWaveSwings: readonly number[] = Array.from(
  { length: OmiMarkGeometry.dotCount },
  (_, i) => pendulumBase + OmiMarkGeometry.laneOf(i),
);

export const omiTusiPendulumSlides: readonly number[] = Array.from(
  { length: OmiMarkGeometry.dotCount },
  (_, i) => tusiPendulumBase + i,
);

export interface OmiPlacementInput {
  motion: OmiOrbMotion;
  index: number;
  turn: number;
  /** The input level for the motions that meter one; ignored by the rest. */
  level?: number;
  /** The progress of the one-shot scatter, 1 when it is not running. */
  burst?: number;
}

/**
 * One dot's placement for one frame. Split out from `omiOrbPlacements` so a
 * test can ask about a single dot's path without allocating the ring.
 */
export function omiDotPlacement({
  motion,
  index,
  turn,
  level = 0,
  burst = 1,
}: OmiPlacementInput): OmiDotPlacement {
  const i = index;
  const G = OmiMarkGeometry;
  const rest = G.radiusOf(i);
  const theta = G.angleOf(i);
  const lift = clamp01(level);

  switch (motion) {
    case 'mark': {
      // A shared breath, offset a little around the ring so the mark never
      // pulses as one flat blob, over the slow orbit it has always had.
      const breath = 0.5 - 0.5 * Math.cos(TAU * ((turn + i / G.dotCount / 3) % 1));
      return {
        offset: scale(G.directionAt(theta + turn * TAU), rest + 2.2 * breath),
        scale: 1 + 0.056 * breath + 0.1 * lift,
        alpha: 0.6 + 0.4 * breath,
      };
    }

    case 'spin':
      return {
        offset: scale(G.directionAt(theta + turn * TAU), rest),
        scale: 1,
        alpha: 0.84,
      };

    case 'pulse': {
      const pulse = OmiThinkingPulse.at(OmiThinkingPulse.localPhase(i, turn));
      return {
        offset: G.restOf(i),
        scale: pulse.scale + 0.1 * lift,
        alpha: pulse.opacity,
      };
    }

    case 'gather': {
      // Pulled in hard, released with an overshoot that carries the dots past
      // their rest radius before they settle — a knot let go, not a knot faded.
      const raw = (turn + i * 0.018) % 1;
      const t = raw < 0 ? raw + 1 : raw;
      let squeeze: number;
      if (t < 0.34) {
        squeeze = easeInCubic.transform(t / 0.34);
      } else if (t < 0.82) {
        squeeze = 1 - easeOutBack.transform((t - 0.34) / 0.48);
      } else {
        squeeze = 0;
      }
      return {
        offset: scale(G.directionAt(theta + turn * TAU), rest * (1 - 0.86 * squeeze)),
        scale: 1 + 0.24 * clamp01(squeeze),
        alpha: 0.62 + 0.38 * (1 - 0.5 * clamp01(squeeze)),
      };
    }

    case 'sine': {
      // Silence leaves the ring standing with a shallow radial ripple; speech
      // flattens it into the chain and drives the amplitude. The morph and the
      // amplitude are both the level, so the wave grows out of the mark rather
      // than replacing it.
      const morph = easeOutCubic.transform(clamp01(lift * 1.7));
      const phase = TAU * (turn * omiSineTravelsPerLap - G.laneOf(i) * omiSineLanePhase);
      const swing = Math.sin(phase);
      const ring = scale(
        G.directionAt(theta),
        rest + 3 * Math.sin(TAU * (turn * 2 - i / G.dotCount)),
      );
      const wave: OmiVec = {
        x: G.laneXOf(i),
        y: G.laneYOf(i) - (12 + 60 * lift) * swing,
      };
      const ringScale = 1 + 0.1 * lift;
      const waveScale = G.laneDotScale + 0.1 * lift + 0.14 * (0.5 + 0.5 * swing);
      return {
        offset: lerpVec(ring, wave, morph),
        scale: ringScale + (waveScale - ringScale) * morph,
        alpha: 0.64 + 0.36 * (0.5 + 0.5 * swing),
      };
    }

    case 'travellingWave': {
      // A gaussian packet running the chain, so the energy is somewhere rather
      // than everywhere: the dots it has left are calm, the dots ahead of it
      // have not moved yet.
      const lane = G.laneOf(i) / (G.dotCount - 1);
      const head = (turn * 2) % 1;
      const gap = Math.abs(lane - head);
      const distance = Math.min(gap, 1 - gap);
      const envelope = Math.exp(-(distance * distance) / (2 * 0.16 * 0.16));
      const swing = Math.sin(TAU * (turn * 3 - lane * 2));
      return {
        offset: {
          x: G.laneXOf(i),
          y: G.laneYOf(i) - (26 + 44 * lift) * envelope * swing,
        },
        scale: G.laneDotScale + 0.26 * envelope,
        alpha: 0.55 + 0.45 * envelope,
      };
    }

    case 'standingWave': {
      // Three half-wavelengths pinned across the chain: the shape is fixed in
      // space and only its amplitude moves, which is what makes the nodes read.
      const lane = G.laneOf(i) / (G.dotCount - 1);
      const shape = Math.sin(Math.PI * lane * 3);
      const beat = Math.sin(TAU * turn * 2);
      return {
        offset: {
          x: G.laneXOf(i),
          y: G.laneYOf(i) - (24 + 40 * lift) * shape * beat,
        },
        scale: G.laneDotScale + 0.2 * Math.abs(shape * beat),
        alpha: 0.58 + 0.42 * Math.abs(shape * beat),
      };
    }

    case 'pendulumWave': {
      // Nine through sixteen swings per lap. Every count is a whole number, so
      // the chain is a flat line again exactly at the lap mark and the desync
      // in between is the whole trick.
      const swings = pendulumBase + G.laneOf(i);
      const swing = Math.sin(TAU * swings * turn);
      return {
        offset: {
          x: G.laneXOf(i),
          y: G.laneYOf(i) - (34 + 30 * lift) * swing,
        },
        scale: G.laneDotScale + 0.16 * Math.abs(swing),
        alpha: 0.6 + 0.4 * Math.abs(swing),
      };
    }

    case 'tusi': {
      // cos(wt + phase) along the dot's own diameter is the degenerate
      // hypocycloid: a circle of half the radius rolling inside the ring at
      // twice the rate, tracing a straight line. The stagger is half the dot's
      // angle, not the whole of it: a full-angle stagger puts opposite dots on
      // the same point for the entire cycle and the ring only ever shows four.
      const slide = Math.cos(TAU * turn * 2 + theta / 2);
      return {
        offset: scale(G.directionAt(theta), rest * slide),
        scale: 1 + 0.14 * (1 - Math.abs(slide)),
        alpha: 0.55 + 0.45 * Math.abs(slide),
      };
    }

    case 'tusiPendulum': {
      // The same diameters, detuned: five through twelve slides per lap. Every
      // dot is still drawing a straight line and every count is still whole, so
      // the lattice tears itself apart and puts itself back together on the lap.
      const slides = tusiPendulumBase + i;
      const slide = Math.cos(TAU * slides * turn + theta / 2);
      return {
        offset: scale(G.directionAt(theta), rest * slide),
        scale: 1 + 0.16 * (1 - Math.abs(slide)),
        alpha: 0.5 + 0.5 * Math.abs(slide),
      };
    }

    case 'audioBars': {
      const lane = G.laneOf(i);
      const bell = 1 - 0.22 * (Math.abs(lane / (G.dotCount - 1) - 0.5) * 2);
      const wobble = 0.5 + 0.5 * Math.sin(TAU * (turn * (2 + lane) + lane * 0.41));
      const height = (0.14 + 0.86 * lift) * bell * (0.18 + 0.82 * wobble);
      return {
        offset: { x: G.laneXOf(i), y: 64 - 128 * height },
        scale: G.laneDotScale * (0.85 + 0.3 * height),
        alpha: 0.58 + 0.42 * height,
      };
    }

    case 'nestedOrbit': {
      // A circle a quarter of the radius rolling without slipping around the
      // inside of the mark: the roll rate is fixed by the circumference ratio,
      // so it reads as a coin rolling rather than a dot on a stick, and four
      // whole cusps fit in a lap — the same four-fold symmetry as the mark.
      const ratio = 1 / 4;
      // Each dot is the same coin at a different moment of the same roll, so
      // the eight of them chase each other around the path instead of riding
      // it as one clump.
      const orbit = TAU * turn + theta;
      const roll = (-orbit * (1 - ratio)) / ratio;
      return {
        offset: add(
          scale(G.directionAt(orbit), rest * (1 - ratio)),
          scale(G.directionAt(roll), rest * ratio),
        ),
        scale: 0.9,
        alpha: 0.66 + 0.34 * (0.5 + 0.5 * Math.cos(orbit - roll)),
      };
    }

    case 'doubleCircle': {
      const outer = i % 2 === 0;
      const angle = theta + turn * TAU * (outer ? 1 : -3);
      return {
        offset: scale(G.directionAt(angle), rest * (outer ? 1 : 0.44)),
        scale: outer ? 1 : 0.82,
        alpha: outer ? 0.95 : 0.68,
      };
    }

    case 'epicycloid': {
      // A circle rolling around the outside. Dot 0 leads and the rest trail it
      // by a fixed lag, so the flourish reads as one spark with a tail.
      const base = rest * 0.6;
      const roller = rest * 0.2;
      const psi = TAU * turn - i * 0.42;
      const k = (base + roller) / roller;
      return {
        offset: {
          x: (base + roller) * Math.sin(psi) - roller * Math.sin(k * psi),
          y: -((base + roller) * Math.cos(psi) - roller * Math.cos(k * psi)),
        },
        scale: 1 + 0.3 * Math.max(0, 1 - i * 0.28),
        alpha: 0.5 + 0.5 * Math.max(0, 1 - i * 0.16),
      };
    }

    case 'lissajous': {
      const p = TAU * turn;
      return {
        offset: {
          x: 74 * Math.sin(2 * p + theta),
          y: -74 * Math.sin(3 * p + theta),
        },
        scale: 1,
        alpha: 0.66 + 0.34 * (0.5 + 0.5 * Math.cos(2 * p + theta)),
      };
    }

    case 'pendulumSwing': {
      // The mark hangs from a point above itself. Each dot reads the swing a
      // few milliseconds late, which is the follow-through.
      const pivot: OmiVec = { x: 0, y: -170 };
      const angle = 0.22 * Math.sin(TAU * (turn - i * 0.006));
      const restAt = G.restOf(i);
      const arm: OmiVec = { x: restAt.x - pivot.x, y: restAt.y - pivot.y };
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      return {
        offset: add(pivot, {
          x: arm.x * cos - arm.y * sin,
          y: arm.x * sin + arm.y * cos,
        }),
        scale: 1,
        alpha: 0.78 + 0.22 * (1 - Math.abs(angle) / 0.22),
      };
    }

    case 'successBurst': {
      // Everything flies out at once and settles back with an eased return, so
      // the ring snaps home rather than drifting home.
      const eased = easeOutBack.transform(clamp01(burst));
      const scatter = burst >= 1 ? 0 : Math.sin(burst * Math.PI) * 34;
      const phase = burst >= 1 ? 0.25 : 1 - burst;
      return {
        offset: scale(G.directionAt(theta + turn * TAU), rest + scatter),
        scale: 1 + phase * 0.16 + 0.1 * lift,
        alpha: (0.6 + phase * 0.4) * (burst >= 1 ? 1 : clamp01(eased)),
      };
    }
  }
}

/**
 * The scatter progress a renderer should feed `motion` at lap position `turn`.
 *
 * `successBurst` is the one motion whose shape lives in `burst` rather than in
 * `turn`: without this it is handed the settled default every frame and never
 * scatters at all. Every other motion is unaffected and gets the settled 1.
 */
export function omiBurstForTurn(motion: OmiOrbMotion, turn: number): number {
  return motion === 'successBurst' ? clamp01(turn) : 1;
}

/**
 * Every dot's placement for one frame of `motion`.
 *
 * `turn` is the position within the current lap, 0 to 1. `level` is the input
 * level for the motions that meter one and is ignored by the rest. `burst` is
 * the progress of the one-shot scatter, 1 when it is not running.
 */
export function omiOrbPlacements({
  motion,
  turn,
  level = 0,
  burst = 1,
}: {
  motion: OmiOrbMotion;
  turn: number;
  level?: number;
  burst?: number;
}): OmiDotPlacement[] {
  return Array.from({ length: OmiMarkGeometry.dotCount }, (_, i) =>
    omiDotPlacement({ motion, index: i, turn, level, burst }),
  );
}
