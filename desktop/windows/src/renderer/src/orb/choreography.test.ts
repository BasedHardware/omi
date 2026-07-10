import { describe, it, expect } from 'vitest'
import {
  DOT_COUNT,
  DEFAULT_ORB_PARAMS,
  ORB_PRESETS,
  easeInOut,
  easeInOutVelocity,
  orbitAngle,
  orbitVelocity,
  mergeBump,
  mergeAmount,
  genesisScale,
  genesisSettled,
  computeOrbFrame
} from './choreography'

const P = DEFAULT_ORB_PARAMS

describe('easeInOut', () => {
  it('is a C-continuous 0→1 S-curve', () => {
    expect(easeInOut(0)).toBe(0)
    expect(easeInOut(1)).toBe(1)
    expect(easeInOut(0.5)).toBeCloseTo(0.5, 6)
    // Monotone non-decreasing.
    let prev = 0
    for (let i = 0; i <= 100; i++) {
      const v = easeInOut(i / 100)
      expect(v).toBeGreaterThanOrEqual(prev - 1e-12)
      prev = v
    }
  })

  it('has the velocity S-curve: zero at both ends, single peak at the middle', () => {
    expect(easeInOutVelocity(0)).toBe(0)
    expect(easeInOutVelocity(1)).toBe(0)
    // Rises to the midpoint peak, then falls — exactly one sign change of slope.
    let last = easeInOutVelocity(0)
    let phase: 'rising' | 'falling' = 'rising'
    for (let i = 1; i <= 100; i++) {
      const v = easeInOutVelocity(i / 100)
      if (phase === 'rising' && v < last - 1e-9) phase = 'falling'
      else if (phase === 'falling') expect(v).toBeLessThanOrEqual(last + 1e-9)
      last = v
    }
    expect(phase).toBe('falling')
    // Peak is at t=0.5.
    expect(easeInOutVelocity(0.5)).toBeCloseTo(1.875, 3)
  })

  it('matches the numerical derivative of easeInOut', () => {
    const h = 1e-6
    for (const t of [0.1, 0.25, 0.5, 0.75, 0.9]) {
      const numeric = (easeInOut(t + h) - easeInOut(t - h)) / (2 * h)
      expect(easeInOutVelocity(t)).toBeCloseTo(numeric, 4)
    }
  })
})

describe('orbitAngle', () => {
  it('advances exactly stepDegrees per cycle and rests between steps', () => {
    const step = (P.stepDegrees * Math.PI) / 180
    expect(orbitAngle(0, P)).toBeCloseTo(0, 9)
    expect(orbitAngle(P.orbitPeriod, P)).toBeCloseTo(step, 9)
    expect(orbitAngle(5 * P.orbitPeriod, P)).toBeCloseTo(5 * step, 9)
    // During the rest tail of a cycle the angle is pinned at the step.
    const restT = P.orbitPeriod * (1 - P.restFraction / 2)
    expect(orbitAngle(restT, P)).toBeCloseTo(step, 9)
    expect(orbitVelocity(restT, P)).toBe(0)
  })

  it('is continuous across cycle boundaries and monotone', () => {
    let prev = orbitAngle(0, P)
    for (let i = 1; i <= 400; i++) {
      const t = (i / 400) * 3 * P.orbitPeriod
      const a = orbitAngle(t, P)
      expect(a).toBeGreaterThanOrEqual(prev - 1e-9)
      expect(a - prev).toBeLessThan(0.2) // no jumps
      prev = a
    }
  })

  it('velocity follows the S-curve within the rotate phase: 0 → peak → 0', () => {
    const rotate = P.orbitPeriod * (1 - P.restFraction)
    expect(orbitVelocity(0, P)).toBe(0)
    expect(orbitVelocity(rotate * 0.999, P)).toBeCloseTo(0, 2)
    const mid = orbitVelocity(rotate / 2, P)
    expect(mid).toBeGreaterThan(orbitVelocity(rotate * 0.1, P))
    expect(mid).toBeGreaterThan(orbitVelocity(rotate * 0.9, P))
  })
})

describe('merge', () => {
  it('mergeBump eases in, holds, eases out', () => {
    expect(mergeBump(0)).toBe(0)
    expect(mergeBump(1)).toBe(0)
    expect(mergeBump(0.5)).toBe(1)
    expect(mergeBump(0.15)).toBeGreaterThan(0)
    expect(mergeBump(0.15)).toBeLessThan(1)
  })

  it('idle merges periodically and fully separates in between', () => {
    // Inside the excursion: merged.
    expect(mergeAmount(P.mergeDuration / 2, 'idle', 0, P)).toBe(1)
    // After the excursion, before the next period: separated.
    expect(mergeAmount(P.mergeDuration + 1, 'idle', 0, P)).toBe(0)
    // Next period repeats.
    expect(mergeAmount(P.mergePeriod + P.mergeDuration / 2, 'idle', 0, P)).toBe(1)
  })

  it('thinking ramps to a held blob; listening/agents stay separated', () => {
    expect(mergeAmount(100, 'thinking', 0, P)).toBe(0)
    expect(mergeAmount(100, 'thinking', 0.4, P)).toBeGreaterThan(0)
    expect(mergeAmount(100, 'thinking', 2, P)).toBe(1)
    expect(mergeAmount(P.mergeDuration / 2, 'listening', 50, P)).toBe(0)
    expect(mergeAmount(P.mergeDuration / 2, 'agents', 50, P)).toBe(0)
  })
})

describe('genesisScale (summon spring)', () => {
  it('starts at 0, ends settled at 1, with a small overshoot (never fade-like)', () => {
    expect(genesisScale(0, P)).toBe(0)
    expect(genesisScale(0.02, P)).toBeGreaterThan(0)
    expect(genesisScale(0.02, P)).toBeLessThan(0.3)
    // Overshoot exists but stays tasteful (< 10%).
    let peak = 0
    for (let i = 0; i <= 300; i++) peak = Math.max(peak, genesisScale(i / 100, P))
    expect(peak).toBeGreaterThan(1)
    expect(peak).toBeLessThan(1.1)
    expect(genesisScale(3, P)).toBeCloseTo(1, 3)
    expect(genesisSettled(3, P)).toBe(true)
    expect(genesisSettled(0.05, P)).toBe(false)
  })

  it('is never negative', () => {
    for (let i = 0; i <= 200; i++) expect(genesisScale(i / 100, P)).toBeGreaterThanOrEqual(0)
  })
})

describe('computeOrbFrame', () => {
  it('always yields 8 dots, inside the disc', () => {
    for (const state of ['idle', 'listening', 'thinking', 'agents'] as const) {
      const f = computeOrbFrame({ t: 7.3, state, stateTime: 2, amplitude: 0.8 })
      expect(f.dots).toHaveLength(DOT_COUNT)
      for (const d of f.dots) {
        const extent = Math.hypot(d.x, d.y) + d.r + d.halfLen
        expect(extent).toBeLessThanOrEqual(1.001) // disc-radius units
      }
    }
  })

  it('listening breathes with amplitude', () => {
    const quiet = computeOrbFrame({ t: 1, state: 'listening', stateTime: 5, amplitude: 0 })
    const loud = computeOrbFrame({ t: 1, state: 'listening', stateTime: 5, amplitude: 1 })
    expect(loud.dots[0].r).toBeGreaterThan(quiet.dots[0].r)
    expect(Math.hypot(loud.dots[0].x, loud.dots[0].y)).toBeGreaterThan(
      Math.hypot(quiet.dots[0].x, quiet.dots[0].y)
    )
  })

  it('thinking pulls dots to the center (merged blob)', () => {
    const f = computeOrbFrame({ t: 100, state: 'thinking', stateTime: 3 })
    expect(f.merge).toBe(1)
    for (const d of f.dots) {
      expect(Math.hypot(d.x, d.y)).toBeLessThan(0.01)
      expect(d.r).toBeGreaterThan(P.dotRadius) // grown while pooled
    }
  })

  it('agents settles dot pairs onto identical centered capsules (four clean pills)', () => {
    const f = computeOrbFrame({ t: 100, state: 'agents', stateTime: 3 })
    const ys = new Set(f.dots.map((d) => d.y.toFixed(4)))
    expect(ys.size).toBe(4) // four rows
    for (const d of f.dots) {
      expect(d.halfLen).toBeCloseTo(P.pillHalfLen, 6)
      expect(d.x).toBeCloseTo(0, 6) // centered — superimposed pair = ONE clean bar
    }
    // Each pair is exactly superimposed (identical primitives, no dumbbell).
    for (let row = 0; row < 4; row++) {
      const a = f.dots[row * 2]
      const b = f.dots[row * 2 + 1]
      expect(a.x).toBeCloseTo(b.x, 9)
      expect(a.y).toBeCloseTo(b.y, 9)
      expect(a.r).toBeCloseTo(b.r, 9)
      expect(a.halfLen).toBeCloseTo(b.halfLen, 9)
    }
  })

  it('mid-merge frames always carry a center pool (no punched-hole artifact)', () => {
    for (const stateTime of [0.3, 0.4, 0.6, 1, 3]) {
      const f = computeOrbFrame({ t: 30, state: 'thinking', stateTime })
      if (f.merge > 0) expect(f.centerR).toBeGreaterThan(0)
    }
    const separated = computeOrbFrame({ t: 12, state: 'idle', stateTime: 12 })
    expect(separated.centerR).toBe(0)
  })

  it('genesis defaults to materialized; genesisTime drives the spring', () => {
    expect(computeOrbFrame({ t: 0, state: 'idle', stateTime: 0 }).genesis).toBe(1)
    expect(
      computeOrbFrame({ t: 0, state: 'idle', stateTime: 0, genesisTime: 0 }).genesis
    ).toBe(0)
  })

  it('all presets produce in-bounds frames across a full cycle', () => {
    for (const params of Object.values(ORB_PRESETS)) {
      for (let i = 0; i < 24; i++) {
        const t = (i / 24) * params.mergePeriod
        const f = computeOrbFrame({ t, state: 'idle', stateTime: t, params })
        for (const d of f.dots) {
          expect(Math.hypot(d.x, d.y) + d.r + d.halfLen).toBeLessThanOrEqual(1.001)
        }
      }
    }
  })
})
