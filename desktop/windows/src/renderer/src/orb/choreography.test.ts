import { describe, it, expect } from 'vitest'
import {
  DOT_COUNT,
  DEFAULT_ORB_PARAMS,
  ORB_PRESETS,
  AMP_FLOOR,
  WAVE_GAIN_MIN,
  WAVE_GAIN_MAX,
  THINK_WAVE_GAIN,
  easeInOut,
  easeInOutVelocity,
  orbitAngle,
  orbitVelocity,
  shapeAmplitude,
  stepAmplitudeEnvelope,
  stepMergeEnvelope,
  mergeAmount,
  spinTargetFor,
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
    let last = easeInOutVelocity(0)
    let phase: 'rising' | 'falling' = 'rising'
    for (let i = 1; i <= 100; i++) {
      const v = easeInOutVelocity(i / 100)
      if (phase === 'rising' && v < last - 1e-9) phase = 'falling'
      else if (phase === 'falling') expect(v).toBeLessThanOrEqual(last + 1e-9)
      last = v
    }
    expect(phase).toBe('falling')
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
      expect(a - prev).toBeLessThan(0.2)
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

describe('bounded amplitude (voice → wave)', () => {
  it('shapeAmplitude maps any input into [AMP_FLOOR, 1] — no spikes, no flatline', () => {
    expect(shapeAmplitude(0)).toBeCloseTo(AMP_FLOOR, 9)
    expect(shapeAmplitude(1)).toBeLessThanOrEqual(1)
    expect(shapeAmplitude(1)).toBeGreaterThan(0.9)
    // Clipping / absurd input saturates at 1, never beyond.
    expect(shapeAmplitude(5)).toBeLessThanOrEqual(1)
    expect(shapeAmplitude(1e6)).toBeLessThanOrEqual(1)
    expect(shapeAmplitude(-3)).toBeCloseTo(AMP_FLOOR, 9)
    // Monotone.
    let prev = 0
    for (let i = 0; i <= 40; i++) {
      const v = shapeAmplitude(i / 20)
      expect(v).toBeGreaterThanOrEqual(prev - 1e-12)
      prev = v
    }
  })

  it('soft knee: compresses the top more than the bottom', () => {
    const low = shapeAmplitude(0.4) - shapeAmplitude(0.2)
    const high = shapeAmplitude(1.0) - shapeAmplitude(0.8)
    expect(high).toBeLessThan(low)
  })

  it('envelope: fast attack, slower release, bounded', () => {
    // Attack from 0 toward 1.
    const attacked = stepAmplitudeEnvelope(0, 1, 0.06)
    // Release from 1 toward 0 over the same dt moves less.
    const released = 1 - stepAmplitudeEnvelope(1, 0, 0.06)
    expect(attacked).toBeGreaterThan(released)
    // Square-wave input stays within [0, 1.5-tolerated] and never overshoots.
    let env = 0
    for (let i = 0; i < 200; i++) {
      env = stepAmplitudeEnvelope(env, i % 20 < 10 ? 1 : 0, 1 / 60)
      expect(env).toBeGreaterThanOrEqual(0)
      expect(env).toBeLessThanOrEqual(1)
    }
  })

  it('waveAmp is bounded for ANY amplitude input (fixed design range)', () => {
    for (const amp of [0, 0.2, 1, 3, 100]) {
      const f = computeOrbFrame({
        t: 9,
        state: 'speaking',
        stateTime: 2,
        speechMerge: 1,
        amplitude: amp
      })
      expect(f.waveAmp).toBeGreaterThanOrEqual(P.noiseAmp * WAVE_GAIN_MIN)
      expect(f.waveAmp).toBeLessThanOrEqual(P.noiseAmp * WAVE_GAIN_MAX)
      expect(f.amplitude).toBeGreaterThanOrEqual(AMP_FLOOR)
      expect(f.amplitude).toBeLessThanOrEqual(1)
    }
  })
})

describe('speech merge envelope', () => {
  it('attacks faster than it releases and clamps to [0,1]', () => {
    let up = 0
    let steps = 0
    while (up < 1 && steps < 1000) {
      up = stepMergeEnvelope(up, 1, 1 / 60)
      steps++
    }
    const attackSteps = steps
    let down = 1
    steps = 0
    while (down > 0 && steps < 1000) {
      down = stepMergeEnvelope(down, 0, 1 / 60)
      steps++
    }
    expect(attackSteps).toBeLessThan(steps) // dissolve is slower than the gather
    expect(stepMergeEnvelope(1, 1, 1)).toBe(1)
    expect(stepMergeEnvelope(0, 0, 1)).toBe(0)
  })
})

describe('mergeAmount', () => {
  it('speaking/listening/idle follow the speechMerge envelope', () => {
    expect(mergeAmount('speaking', 5, 0)).toBe(0)
    expect(mergeAmount('speaking', 5, 1)).toBe(1)
    expect(mergeAmount('listening', 5, 0.5)).toBeCloseTo(easeInOut(0.5), 9)
    expect(mergeAmount('idle', 5, 0)).toBe(0)
  })

  it('thinking is autonomous (ignores speech), agents never merges', () => {
    expect(mergeAmount('thinking', 0, 1)).toBe(0)
    expect(mergeAmount('thinking', 2, 0)).toBe(1)
    expect(mergeAmount('agents', 5, 1)).toBe(0)
  })

  // C6: with enterMerge supplied, a state change cross-fades from the value on
  // screen instead of snapping (blob explode-and-reform).
  describe('cross-fade on state change (enterMerge)', () => {
    it('is exactly continuous with the value shown at the switch instant', () => {
      // At stateTime 0 the new state must return precisely enterMerge.
      for (const state of ['idle', 'listening', 'speaking', 'thinking', 'agents'] as const) {
        for (const em of [0, 0.3, 1]) {
          expect(mergeAmount(state, 0, 0, em)).toBeCloseTo(em, 9)
        }
      }
    })

    it('speaking→thinking never snaps: entering thinking merged stays merged', () => {
      // enterMerge≈1 (a held speech blob) → thinking holds ~1 the whole ramp,
      // never dips toward 0 the way the branch-switch bug did.
      for (let s = 0; s <= 0.8; s += 0.05) {
        expect(mergeAmount('thinking', s, 0, 1)).toBeGreaterThan(0.98)
      }
    })

    it('thinking→idle dissolves smoothly from 1 down to 0', () => {
      const start = mergeAmount('idle', 0, 0, 1)
      const end = mergeAmount('idle', 0.6, 0, 1)
      expect(start).toBeCloseTo(1, 9)
      expect(end).toBeLessThan(0.02)
      // Monotone, no reversal, bounded per-step (no snap) at 60fps.
      let prev = start
      for (let s = 1 / 60; s <= 0.6; s += 1 / 60) {
        const m = mergeAmount('idle', s, 0, 1)
        expect(m).toBeLessThanOrEqual(prev + 1e-9)
        expect(prev - m).toBeLessThan(0.12)
        prev = m
      }
    })

    it('thinking from the ring (enterMerge 0) reduces exactly to the original ramp', () => {
      // thinking's steady target is 1, so cross-fading 0→1 over its 0.8s gather
      // IS the original easeInOut(stateTime/0.8).
      for (let s = 0; s <= 1; s += 0.1) {
        expect(mergeAmount('thinking', s, 0, 0)).toBeCloseTo(mergeAmount('thinking', s, 0), 9)
      }
    })

    it('envelope-driven states converge to the original once the cross-fade completes', () => {
      // Entering idle with enterMerge 0 briefly ramps 0→envelope, then matches
      // the plain envelope value after MERGE_XFADE (0.4s).
      for (let s = 0.4; s <= 1; s += 0.1) {
        expect(mergeAmount('idle', s, 0.5, 0)).toBeCloseTo(mergeAmount('idle', s, 0.5), 9)
      }
    })
  })
})

describe('spinTargetFor (state-speed choreography)', () => {
  it('idle and agents rest at 1×; busy states spin faster, thinking the most', () => {
    const busy = DEFAULT_ORB_PARAMS.spinBusyMult
    expect(spinTargetFor('idle', P)).toBe(1)
    expect(spinTargetFor('agents', P)).toBe(1)
    expect(spinTargetFor('thinking', P)).toBe(busy)
    // speaking > listening > idle, all below thinking.
    expect(spinTargetFor('speaking', P)).toBeGreaterThan(spinTargetFor('listening', P))
    expect(spinTargetFor('listening', P)).toBeGreaterThan(1)
    expect(spinTargetFor('speaking', P)).toBeLessThan(spinTargetFor('thinking', P))
  })

  it('compact mounts spin up more gently than the default', () => {
    expect(spinTargetFor('thinking', ORB_PRESETS.compact)).toBeLessThan(
      spinTargetFor('thinking', P)
    )
  })
})

describe('genesisScale (summon spring)', () => {
  it('starts at 0, ends settled at 1, with a small overshoot (never fade-like)', () => {
    expect(genesisScale(0, P)).toBe(0)
    expect(genesisScale(0.02, P)).toBeGreaterThan(0)
    expect(genesisScale(0.02, P)).toBeLessThan(0.3)
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
    for (const state of ['idle', 'listening', 'speaking', 'thinking', 'agents'] as const) {
      const f = computeOrbFrame({ t: 7.3, state, stateTime: 2, amplitude: 0.8, speechMerge: 1 })
      expect(f.dots).toHaveLength(DOT_COUNT)
      for (const d of f.dots) {
        const extent = Math.hypot(d.x, d.y) + d.r + d.halfLen
        expect(extent).toBeLessThanOrEqual(1.001)
      }
    }
  })

  it('speaking conglomerates: full speechMerge pulls every dot to the center pool', () => {
    const f = computeOrbFrame({
      t: 100,
      state: 'speaking',
      stateTime: 3,
      speechMerge: 1,
      amplitude: 0.6
    })
    expect(f.merge).toBe(1)
    expect(f.centerR).toBeGreaterThan(0)
    for (const d of f.dots) {
      expect(Math.hypot(d.x, d.y)).toBeLessThan(0.01)
      expect(d.r).toBeGreaterThan(P.dotRadius)
    }
  })

  it('the speech wave tracks amplitude; the pool swells with the voice', () => {
    const quiet = computeOrbFrame({
      t: 9,
      state: 'speaking',
      stateTime: 3,
      speechMerge: 1,
      amplitude: 0
    })
    const loud = computeOrbFrame({
      t: 9,
      state: 'speaking',
      stateTime: 3,
      speechMerge: 1,
      amplitude: 1
    })
    expect(loud.waveAmp).toBeGreaterThan(quiet.waveAmp)
    expect(loud.centerR).toBeGreaterThan(quiet.centerR)
  })

  it('thinking is DISTINCT from the speech blob: tighter pool, fixed lower wave, no audio coupling', () => {
    const think0 = computeOrbFrame({ t: 9, state: 'thinking', stateTime: 3, amplitude: 0 })
    const think1 = computeOrbFrame({ t: 9, state: 'thinking', stateTime: 3, amplitude: 1 })
    const speak = computeOrbFrame({
      t: 9,
      state: 'speaking',
      stateTime: 3,
      speechMerge: 1,
      amplitude: 0.9
    })
    // Zero audio coupling.
    expect(think1.waveAmp).toBe(think0.waveAmp)
    expect(think1.centerR).toBe(think0.centerR)
    expect(think0.waveAmp).toBeCloseTo(P.noiseAmp * THINK_WAVE_GAIN, 9)
    // Tighter + calmer than a loud speech blob.
    expect(think0.centerR).toBeLessThan(speak.centerR)
    expect(think0.waveAmp).toBeLessThan(speak.waveAmp)
  })

  it('quiet listening keeps the calm ring (no merge without a speech signal)', () => {
    const f = computeOrbFrame({ t: 12, state: 'listening', stateTime: 5, amplitude: 0.4 })
    expect(f.merge).toBe(0)
    expect(f.centerR).toBe(0)
    for (const d of f.dots) {
      expect(Math.hypot(d.x, d.y)).toBeCloseTo(P.orbitRadius, 6)
    }
  })

  it('agents settles dot pairs onto identical centered capsules (four clean pills)', () => {
    const f = computeOrbFrame({ t: 100, state: 'agents', stateTime: 3 })
    const ys = new Set(f.dots.map((d) => d.y.toFixed(4)))
    expect(ys.size).toBe(4)
    for (const d of f.dots) {
      expect(d.halfLen).toBeCloseTo(P.pillHalfLen, 6)
      expect(d.x).toBeCloseTo(0, 6)
    }
    // Rows are assigned by ring y-order (not index): group by y — each row
    // must hold EXACTLY two superimposed identical primitives (one clean bar).
    const rows = new Map<string, typeof f.dots>()
    for (const d of f.dots) {
      const key = d.y.toFixed(6)
      rows.set(key, [...(rows.get(key) ?? []), d])
    }
    expect(rows.size).toBe(4)
    for (const pair of rows.values()) {
      expect(pair).toHaveLength(2)
      expect(pair[0].x).toBeCloseTo(pair[1].x, 9)
      expect(pair[0].r).toBeCloseTo(pair[1].r, 9)
      expect(pair[0].halfLen).toBeCloseTo(pair[1].halfLen, 9)
    }
  })

  it('agents transition is staged: the glide settles before any stretch begins', () => {
    // While any dot is still gliding (off its row-center x=0... y=row), no
    // capsule stretch may be engaged — stretching mid-glide bridged pills
    // across rows (review round 2).
    const rowYs = [0, 1, 2, 3].map((row) => (row - 1.5) * P.pillRowPitch)
    for (let s = 0.05; s < 0.7; s += 0.05) {
      const f = computeOrbFrame({ t: 100, state: 'agents', stateTime: s })
      const stretched = f.dots.some((d) => d.halfLen > 1e-3)
      if (!stretched) continue
      // Once any stretch is engaged, every dot must already be settled on a
      // row center (x=0, y = one of the four rows).
      for (const d of f.dots) {
        expect(Math.abs(d.x)).toBeLessThan(1e-3)
        expect(Math.min(...rowYs.map((y) => Math.abs(d.y - y)))).toBeLessThan(1e-3)
      }
    }
  })

  it('the center pool stays at zero until the dots cover the center (no floating speck)', () => {
    // The pool is a separate primitive: if it appears while the dots are still a
    // spread ring it renders as an isolated center speck — a phantom 9th dot
    // (skeptical-review Critical). Its onset is held back until the leading
    // (staggered) dot has converged onto the center, so the pool is always
    // absorbed by a dot, never isolated, and its area grows in continuously
    // (no hard floor to jump across mid-dissolve — C6). Below the onset it must
    // be EXACTLY zero; a fully held blob must have a pool filling its interior.
    for (let m = 0; m <= 1.0001; m += 0.02) {
      const f = computeOrbFrame({ t: 0.41, state: 'speaking', stateTime: 1, speechMerge: m })
      if (f.merge < 0.3) expect(f.centerR).toBe(0)
    }
    const held = computeOrbFrame({ t: 0.41, state: 'speaking', stateTime: 1, speechMerge: 1 })
    expect(held.centerR).toBeGreaterThan(0.02)
  })

  it('genesis defaults to materialized; genesisTime drives the spring', () => {
    expect(computeOrbFrame({ t: 0, state: 'idle', stateTime: 0 }).genesis).toBe(1)
    expect(computeOrbFrame({ t: 0, state: 'idle', stateTime: 0, genesisTime: 0 }).genesis).toBe(0)
  })

  it('all presets produce in-bounds frames across speech and orbit', () => {
    for (const params of Object.values(ORB_PRESETS)) {
      for (let i = 0; i < 24; i++) {
        const t = (i / 24) * 12
        const f = computeOrbFrame({
          t,
          state: 'speaking',
          stateTime: t,
          speechMerge: (i % 12) / 11,
          amplitude: 1,
          params
        })
        for (const d of f.dots) {
          expect(Math.hypot(d.x, d.y) + d.r + d.halfLen).toBeLessThanOrEqual(1.001)
        }
      }
    }
  })
})
