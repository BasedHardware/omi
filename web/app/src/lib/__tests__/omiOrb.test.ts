import { describe, expect, it } from 'vitest';
import {
  CubicEasing,
  OmiMarkGeometry,
  OmiThinkingPulse,
  easeInCubic,
  easeOutBack,
  easeOutCubic,
  omiDotPlacementLerp,
  omiMotionForState,
  omiMotionsForState,
  omiOrbPlacements,
  omiPendulumWaveSwings,
  omiSineLanePhase,
  omiSineTravelsPerLap,
  smoothOmiLevel,
  omiTusiPendulumSlides,
  type OmiOrbMotion,
  type OmiOrbState,
} from '@/lib/omiOrb';

/** A spread of lap positions, so a claim has to hold for the whole cycle. */
const SAMPLES = [0, 0.07, 0.19, 0.25, 0.33, 0.5, 0.62, 0.75, 0.88, 0.97, 1];

const ALL_MOTIONS: OmiOrbMotion[] = [
  'mark',
  'spin',
  'pulse',
  'gather',
  'sine',
  'travellingWave',
  'standingWave',
  'pendulumWave',
  'tusiPendulum',
  'audioBars',
  'tusi',
  'nestedOrbit',
  'doubleCircle',
  'epicycloid',
  'lissajous',
  'pendulumSwing',
  'successBurst',
];

const ALL_STATES: OmiOrbState[] = [
  'idle',
  'loading',
  'thinking',
  'searching',
  'streaming',
  'speaking',
  'listening',
  'success',
];

const at = (motion: OmiOrbMotion, turn: number, level = 0) =>
  omiOrbPlacements({ motion, turn, level });

const length = (v: { x: number; y: number }) => Math.hypot(v.x, v.y);

describe('CubicEasing', () => {
  it('pins the endpoints and stays monotonic in between', () => {
    for (const curve of [easeInCubic, easeOutBack, easeOutCubic]) {
      expect(curve.transform(0)).toBe(0);
      expect(curve.transform(1)).toBe(1);
    }
    // easeOutBack overshoots past 1 on the way, so only the input-monotonic
    // curves are checked for a monotonic output.
    for (const curve of [easeInCubic, easeOutCubic]) {
      let previous = -1;
      for (let s = 0; s <= 100; s++) {
        const value = curve.transform(s / 100);
        expect(value).toBeGreaterThanOrEqual(previous);
        previous = value;
      }
    }
  });

  it('matches the linear curve exactly, where the answer is known', () => {
    const linear = new CubicEasing(1 / 3, 1 / 3, 2 / 3, 2 / 3);
    for (const x of [0.1, 0.25, 0.4, 0.5, 0.73, 0.9]) {
      expect(linear.transform(x)).toBeCloseTo(x, 6);
    }
  });

  it('overshoots past 1 for easeOutBack, as Flutter does', () => {
    const peak = Math.max(
      ...Array.from({ length: 101 }, (_, s) => easeOutBack.transform(s / 100)),
    );
    expect(peak).toBeGreaterThan(1);
  });

  it('clamps outside the unit interval', () => {
    expect(easeOutCubic.transform(-1)).toBe(0);
    expect(easeOutCubic.transform(2)).toBe(1);
  });
});

describe('smoothOmiLevel', () => {
  it('eases raw meter changes over animation frames', () => {
    const attack = smoothOmiLevel(0, 1, 16);
    const release = smoothOmiLevel(1, 0, 16);

    expect(attack).toBeGreaterThan(0);
    expect(attack).toBeLessThan(1);
    expect(release).toBeGreaterThan(0);
    expect(release).toBeLessThan(1);
    expect(attack).toBeGreaterThan(1 - release);
  });

  it('clamps invalid source values before smoothing', () => {
    expect(smoothOmiLevel(-1, 2, 100)).toBeGreaterThan(0);
    expect(smoothOmiLevel(2, -1, 100)).toBeLessThan(1);
  });
});

describe('OmiThinkingPulse', () => {
  it('matches the site keyframe endpoints', () => {
    expect(OmiThinkingPulse.at(0)).toEqual({ opacity: 0.62, scale: 1 });
    expect(OmiThinkingPulse.at(0.12).opacity).toBeCloseTo(1, 3);
    expect(OmiThinkingPulse.at(0.12).scale).toBeCloseTo(1.14, 3);
    expect(OmiThinkingPulse.at(0.7)).toEqual({ opacity: 0.62, scale: 1 });
    expect(OmiThinkingPulse.at(0.99)).toEqual({ opacity: 0.62, scale: 1 });
  });

  it('staggers the peaks around the ring', () => {
    const peaks = Array.from(
      { length: OmiMarkGeometry.dotCount },
      (_, i) => OmiThinkingPulse.at(OmiThinkingPulse.localPhase(i, 0.12)).opacity,
    );
    expect(peaks.indexOf(Math.max(...peaks))).toBe(0);
  });
});

describe('OmiMarkGeometry', () => {
  it('places the axis dots at 86.71 and the diagonals at 91.92', () => {
    expect(OmiMarkGeometry.restOf(0).y).toBeCloseTo(-86.71, 9);
    expect(OmiMarkGeometry.restOf(2).x).toBeCloseTo(86.71, 9);
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      const expected = i % 2 === 0 ? 86.71 : 91.92;
      expect(OmiMarkGeometry.radiusOf(i)).toBe(expected);
      expect(length(OmiMarkGeometry.restOf(i))).toBeCloseTo(expected, 9);
    }
  });

  it('unrolls the ring into SW, W, NW, N, NE, E, SE, S', () => {
    const lanes = Array.from({ length: OmiMarkGeometry.dotCount }, (_, i) =>
      OmiMarkGeometry.laneOf(i),
    );
    expect(lanes).toEqual([3, 4, 5, 6, 7, 0, 1, 2]);
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      expect(OmiMarkGeometry.laneOf(i)).toBe((i + 3) % 8);
    }
    expect(new Set(lanes).size).toBe(OmiMarkGeometry.dotCount);
    // Ring order and lane order advance together, which is what keeps a
    // travelling wave travelling in the same direction through the morph.
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      const next = (i + 1) % OmiMarkGeometry.dotCount;
      expect((lanes[next]! - lanes[i]! + 8) % 8).toBe(1);
    }
    // The chain is cut at the bottom, so due south is the far right lane.
    expect(OmiMarkGeometry.laneOf(4)).toBe(OmiMarkGeometry.dotCount - 1);
    expect(OmiMarkGeometry.laneXOf(4)).toBeCloseTo(OmiMarkGeometry.laneSpan, 9);
    expect(OmiMarkGeometry.laneXOf(5)).toBeCloseTo(-OmiMarkGeometry.laneSpan, 9);
  });
});

describe('every motion', () => {
  it('places eight finite, drawable dots at every point in the lap', () => {
    for (const motion of ALL_MOTIONS) {
      for (const turn of SAMPLES) {
        for (const level of [0, 0.4, 1]) {
          const dots = at(motion, turn, level);
          expect(dots).toHaveLength(OmiMarkGeometry.dotCount);
          for (const dot of dots) {
            const where = `${motion} @ turn ${turn} level ${level}`;
            expect(Number.isFinite(dot.offset.x), where).toBe(true);
            expect(Number.isFinite(dot.offset.y), where).toBe(true);
            expect(dot.scale, where).toBeGreaterThan(0);
            expect(dot.scale, where).toBeLessThan(2);
            expect(dot.alpha, where).toBeGreaterThanOrEqual(0);
            expect(dot.alpha, where).toBeLessThanOrEqual(1);
            // Nothing may wander outside the mark's own canvas, or a small orb
            // would clip its dots against its own box.
            expect(length(dot.offset), where).toBeLessThanOrEqual(
              OmiMarkGeometry.canvas / 2,
            );
          }
        }
      }
    }
  });

  it('is continuous across the lap boundary', () => {
    for (const motion of ALL_MOTIONS) {
      const end = at(motion, 0.999);
      const start = at(motion, 0);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        const drift = Math.hypot(
          end[i]!.offset.x - start[i]!.offset.x,
          end[i]!.offset.y - start[i]!.offset.y,
        );
        expect(drift, `${motion} jumps at the lap mark on dot ${i}`).toBeLessThan(6);
      }
    }
  });
});

describe('mark', () => {
  it('keeps the brand radii, breathing by a couple of units at most', () => {
    for (const turn of SAMPLES) {
      const dots = at('mark', turn);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        const delta = length(dots[i]!.offset) - OmiMarkGeometry.radiusOf(i);
        expect(delta).toBeGreaterThanOrEqual(-1e-9);
        expect(delta).toBeLessThanOrEqual(2.2 + 1e-9);
      }
    }
  });

  it('turns exactly one lap', () => {
    const quarter = at('mark', 0.25);
    expect(quarter[0]!.offset.x).toBeGreaterThan(0);
    expect(Math.abs(quarter[0]!.offset.y)).toBeLessThan(1);
  });
});

describe('tusi couple', () => {
  it('keeps every dot on its own diameter through the centre', () => {
    for (const motion of ['tusi', 'tusiPendulum'] as const) {
      for (const turn of SAMPLES) {
        const dots = at(motion, turn);
        for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
          const line = OmiMarkGeometry.directionAt(OmiMarkGeometry.angleOf(i));
          const p = dots[i]!.offset;
          // Zero cross product with the rest direction: the point is on the
          // line through the centre, which is the whole claim of the couple.
          expect(p.x * line.y - p.y * line.x).toBeCloseTo(0, 9);
          expect(length(p)).toBeLessThanOrEqual(OmiMarkGeometry.radiusOf(i) + 1e-9);
        }
      }
    }
  });

  it('sweeps a full diameter each half lap', () => {
    expect(at('tusi', 0)[0]!.offset.y).toBeCloseTo(-OmiMarkGeometry.axisRadius, 9);
    expect(length(at('tusi', 0.125)[0]!.offset)).toBeCloseTo(0, 9);
    expect(at('tusi', 0.25)[0]!.offset.y).toBeCloseTo(OmiMarkGeometry.axisRadius, 9);
  });

  it('gives tusiPendulum whole, distinct slide counts so it resynchronises', () => {
    // Whole slide counts are the mechanism: one non-integer and the lattice
    // never comes back together.
    for (const slides of omiTusiPendulumSlides) {
      expect(Number.isInteger(slides)).toBe(true);
      expect(slides).toBeGreaterThan(0);
    }
    expect(new Set(omiTusiPendulumSlides).size).toBe(OmiMarkGeometry.dotCount);
    const start = at('tusiPendulum', 0);
    const end = at('tusiPendulum', 1);
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      expect(end[i]!.offset.x).toBeCloseTo(start[i]!.offset.x, 9);
      expect(end[i]!.offset.y).toBeCloseTo(start[i]!.offset.y, 9);
    }
  });

  it('desynchronises in between, or it would just be a spin', () => {
    const widest = Math.max(
      ...Array.from({ length: 200 }, (_, s) => {
        const dots = at('tusiPendulum', s / 200);
        const radii = dots.map((d, i) => length(d.offset) / OmiMarkGeometry.radiusOf(i));
        return Math.max(...radii) - Math.min(...radii);
      }),
    );
    expect(widest).toBeGreaterThan(0.9);
  });
});

describe('pendulum wave', () => {
  it('gives every lane its own whole number of swings', () => {
    for (const swings of omiPendulumWaveSwings) {
      expect(Number.isInteger(swings)).toBe(true);
      expect(swings).toBeGreaterThan(0);
    }
    expect(new Set(omiPendulumWaveSwings).size).toBe(OmiMarkGeometry.dotCount);
  });

  it('is a flat line at both ends of the lap and scattered in between', () => {
    for (const turn of [0, 1]) {
      const line = at('pendulumWave', turn);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        expect(line[i]!.offset.y).toBeCloseTo(OmiMarkGeometry.laneYOf(i), 9);
      }
    }
    const spread = at('pendulumWave', 0.29).map((d) => d.offset.y);
    expect(Math.max(...spread) - Math.min(...spread)).toBeGreaterThan(20);
  });

  it('holds the lanes in x so only the swing reads', () => {
    for (const turn of SAMPLES) {
      const dots = at('pendulumWave', turn);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        expect(dots[i]!.offset.x).toBeCloseTo(OmiMarkGeometry.laneXOf(i), 9);
      }
    }
  });
});

describe('sine', () => {
  it('is still the ring in silence', () => {
    for (const turn of SAMPLES) {
      const dots = at('sine', turn, 0);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        expect(
          Math.abs(length(dots[i]!.offset) - OmiMarkGeometry.radiusOf(i)),
        ).toBeLessThanOrEqual(3.0001);
      }
    }
  });

  it('flattens onto the chain and fits a sine when spoken into', () => {
    const dots = at('sine', 0.31, 1);
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      expect(dots[i]!.offset.x).toBeCloseTo(OmiMarkGeometry.laneXOf(i), 1);
    }
    const amplitude = 12 + 60;
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      const phase =
        2 *
        Math.PI *
        (0.31 * omiSineTravelsPerLap - OmiMarkGeometry.laneOf(i) * omiSineLanePhase);
      expect(dots[i]!.offset.y - OmiMarkGeometry.laneYOf(i)).toBeCloseTo(
        -amplitude * Math.sin(phase),
        0,
      );
    }
  });

  it('travels one way along the chain', () => {
    const heightOfLane = (lane: number, turn: number) => {
      const i = Array.from({ length: OmiMarkGeometry.dotCount }, (_, n) => n).find(
        (n) => OmiMarkGeometry.laneOf(n) === lane,
      )!;
      return at('sine', turn, 1)[i]!.offset.y - OmiMarkGeometry.laneYOf(i);
    };
    const step = omiSineLanePhase / omiSineTravelsPerLap;
    expect(heightOfLane(1, 0.2 + step)).toBeCloseTo(heightOfLane(0, 0.2), 2);
  });
});

describe('double circle', () => {
  it('holds the axes out and pulls the diagonals in, counter-turning', () => {
    for (const turn of SAMPLES) {
      const dots = at('doubleCircle', turn);
      for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
        expect(length(dots[i]!.offset)).toBeCloseTo(
          OmiMarkGeometry.radiusOf(i) * (i % 2 === 0 ? 1 : 0.44),
          9,
        );
      }
    }
    const a = at('doubleCircle', 0);
    const b = at('doubleCircle', 0.02);
    const sweep = (i: number) =>
      a[i]!.offset.x * b[i]!.offset.y - a[i]!.offset.y * b[i]!.offset.x;
    expect(Math.sign(sweep(0))).not.toBe(Math.sign(sweep(1)));
  });
});

describe('gather', () => {
  it('collapses toward the centre and springs back past rest', () => {
    for (let i = 0; i < OmiMarkGeometry.dotCount; i++) {
      const radii = Array.from({ length: 101 }, (_, s) =>
        length(at('gather', s / 100)[i]!.offset),
      );
      expect(Math.min(...radii)).toBeLessThan(OmiMarkGeometry.radiusOf(i) * 0.25);
      expect(Math.max(...radii)).toBeGreaterThan(OmiMarkGeometry.radiusOf(i));
    }
  });
});

describe('successBurst', () => {
  it('scatters mid-burst and sits on the ring once it is over', () => {
    const mid = omiOrbPlacements({ motion: 'successBurst', turn: 0, burst: 0.5 });
    expect(length(mid[0]!.offset)).toBeGreaterThan(OmiMarkGeometry.axisRadius);
    const done = omiOrbPlacements({ motion: 'successBurst', turn: 0 });
    expect(length(done[0]!.offset)).toBeCloseTo(OmiMarkGeometry.axisRadius, 9);
  });
});

describe('state mapping', () => {
  it('gives every state at least one motion', () => {
    for (const state of ALL_STATES) {
      expect(omiMotionsForState[state]?.length ?? 0).toBeGreaterThan(0);
    }
  });

  it('reserves the wave for hearing you', () => {
    for (const state of ALL_STATES) {
      if (state === 'listening') continue;
      expect(omiMotionsForState[state]).not.toContain('sine');
    }
    expect(omiMotionsForState.listening).toEqual(['sine']);
  });

  it('keeps idle on the mark and success on the burst', () => {
    expect(omiMotionForState('idle')).toBe('mark');
    expect(omiMotionForState('success')).toBe('successBurst');
  });

  it('varies the motion between waits, never within one', () => {
    const seen = new Set(
      Array.from({ length: 12 }, (_, seed) => omiMotionForState('thinking', seed)),
    );
    expect(seen.size).toBeGreaterThan(1);
    for (let seed = 0; seed < 12; seed++) {
      expect(omiMotionForState('thinking', seed)).toBe(
        omiMotionForState('thinking', seed),
      );
    }
  });

  it('keeps a negative seed in range', () => {
    for (const state of ALL_STATES) {
      expect(omiMotionsForState[state]).toContain(omiMotionForState(state, -7));
    }
  });
});

describe('omiDotPlacementLerp', () => {
  it('lerps every channel', () => {
    const half = omiDotPlacementLerp(
      { offset: { x: 0, y: 0 }, scale: 1, alpha: 0 },
      { offset: { x: 10, y: 20 }, scale: 2, alpha: 1 },
      0.5,
    );
    expect(half.offset).toEqual({ x: 5, y: 10 });
    expect(half.scale).toBe(1.5);
    expect(half.alpha).toBe(0.5);
  });
});
