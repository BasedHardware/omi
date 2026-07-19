import { describe, it, expect } from 'vitest'
import {
  AmplitudeMapper,
  AMP_OUT_CEIL,
  AMP_NO_SIGNAL,
  CEIL_MIN_SPAN_DB,
  GATE_LO_DB,
  GATE_HI_DB
} from './amplitudeMapper'

// The acceptance table (the "feel spec" from the amplitude-mapping fix brief),
// replayed as scripted sessions. Levels are linear full-scale amplitudes — the
// canonical unit every producer now emits (hub pcmPeakLevel, capture-window
// time-domain peak): dB = 20·log10(x), so 0.01 ≈ -40 dBFS, 0.1 ≈ -20, 0.5 ≈ -6.

const DT = 1 / 30 // the Orb samples amplitude ~30Hz

const lin = (db: number): number => Math.pow(10, db / 20)

/** Run `seconds` of a constant raw level through the mapper, returning the last
 *  output (the settled response to that level). */
function run(m: AmplitudeMapper, rawLin: number, seconds: number): number {
  let out = 0
  for (let t = 0; t < seconds; t += DT) out = m.step(rawLin, DT)
  return out
}

/** A mapper "warmed up" like a real session: a beat of room silence, then a few
 *  seconds of normal speech so the trackers have seen a normal mic. */
function warmedMapper(): AmplitudeMapper {
  const m = new AmplitudeMapper()
  run(m, lin(-50), 1.0) // room floor
  run(m, lin(-14), 3.0) // normal speech peaks
  run(m, lin(-50), 0.5)
  return m
}

describe('AmplitudeMapper acceptance table', () => {
  it('silence settles at 0 — no idle jitter dance', () => {
    const m = warmedMapper()
    expect(run(m, lin(-60), 1)).toBe(0)
    expect(run(m, lin(-50), 1)).toBe(0) // room noise
    expect(m.step(0, DT)).toBe(0) // literal no-signal
    expect(m.step(AMP_NO_SIGNAL / 2, DT)).toBe(0)
  })

  it('breath / hiss just above the room floor still rests (gate margin)', () => {
    const m = warmedMapper()
    expect(run(m, lin(-45), 0.3)).toBe(0) // floor -50 + margin 10 → -40, clamped to GATE_HI -44
  })

  it('quiet speech is clearly visible, well below max', () => {
    const m = warmedMapper()
    const quiet = run(m, lin(-32), 0.5)
    expect(quiet).toBeGreaterThan(0.15) // visibly moves the dots
    expect(quiet).toBeLessThan(0.6) // …but nowhere near the ceiling
  })

  it('normal speech lives mid-to-high with visible dynamics across syllables', () => {
    const m = warmedMapper()
    const soft = run(m, lin(-24), 0.2)
    const mid = run(m, lin(-18), 0.2)
    const peak = run(m, lin(-13), 0.2)
    expect(soft).toBeGreaterThan(0.35)
    expect(peak).toBeLessThanOrEqual(AMP_OUT_CEIL)
    expect(peak).toBeGreaterThan(0.75)
    // Dynamics: distinct syllable loudnesses land at visibly distinct levels.
    expect(mid - soft).toBeGreaterThan(0.08)
    expect(peak - mid).toBeGreaterThan(0.08)
  })

  it('loud speech approaches the max but never slams/pins it', () => {
    const m = warmedMapper()
    let maxOut = 0
    for (let t = 0; t < 3; t += DT) maxOut = Math.max(maxOut, m.step(lin(-6), DT))
    expect(maxOut).toBeGreaterThan(0.8) // near max
    expect(maxOut).toBeLessThanOrEqual(AMP_OUT_CEIL) // structural headroom
    expect(AMP_OUT_CEIL).toBeLessThan(1)
    // Sustained loud settles slightly BELOW the touch peak (ceiling adapts up).
    const settled = run(m, lin(-6), 4)
    expect(settled).toBeLessThanOrEqual(maxOut + 1e-9)
    expect(settled).toBeGreaterThan(0.7)
  })

  // Regression for the 2026-07-18 top-end trim ("visualizer maxes out a bit"):
  // with 4dB of headroom every emphasized syllable (a few dB over the tracked
  // ceiling) clamped to the cap. Session-typical peaks must ride high but
  // visibly OFF the cap, ordinary emphasis must keep margin, and only a genuine
  // outlier (> CEIL_HEADROOM_DB over the session ceiling) reaches OUT_CEIL.
  it('session-typical peaks ride high without slamming the cap', () => {
    const m = warmedMapper()
    run(m, lin(-13), 4) // let the ceiling settle onto this session's peaks
    const typical = run(m, lin(-13), 0.3)
    expect(typical).toBeGreaterThan(0.7)
    expect(typical).toBeLessThan(0.85)
    // Ordinary emphasis (+4dB over the session ceiling) still keeps margin…
    expect(m.step(lin(-9), DT)).toBeLessThan(AMP_OUT_CEIL - 0.02)
    // …only a genuine outlier (>7dB over) touches the cap.
    expect(m.step(lin(-2), DT)).toBeCloseTo(AMP_OUT_CEIL, 5)
  })

  it('a quiet→loud sweep grows monotonically', () => {
    const m = warmedMapper()
    let prev = -1
    for (let i = 0; i <= 60; i++) {
      const db = -50 + (44 * i) / 60 // -50 → -6 dBFS over 2s
      const out = m.step(lin(db), DT)
      expect(out).toBeGreaterThanOrEqual(prev - 1e-9)
      prev = out
    }
    expect(prev).toBeGreaterThan(0.8)
  })

  it('output is bounded for ANY input (hot input tolerated, never > OUT_CEIL)', () => {
    const m = new AmplitudeMapper()
    for (const raw of [0, 1e-6, 0.001, 0.5, 1, 2, 100]) {
      const out = run(m, raw, 0.5)
      expect(out).toBeGreaterThanOrEqual(0)
      expect(out).toBeLessThanOrEqual(AMP_OUT_CEIL)
    }
  })
})

describe('AmplitudeMapper bounded-gain AGC properties', () => {
  it('quiet-room noise can NEVER be normalized above the rest level (the old "maxed out constantly" era)', () => {
    const m = new AmplitudeMapper()
    // Minutes of nothing but room noise: the AGC must not stretch it to bars.
    let maxOut = 0
    for (let t = 0; t < 120; t += DT) maxOut = Math.max(maxOut, m.step(lin(-48), DT))
    expect(maxOut).toBe(0)
  })

  it('a whisper-only session stays visibly quiet — bounded normalization gain', () => {
    const m = new AmplitudeMapper()
    run(m, lin(-55), 2) // very quiet room
    // Minutes of whisper-level speech: the ceiling may decay toward it, but the
    // min-span clamp keeps whispers from ever reading as full-range speech.
    let settled = 0
    for (let t = 0; t < 120; t += DT) settled = m.step(lin(-36), DT)
    expect(settled).toBeGreaterThan(0.1) // still visible…
    expect(settled).toBeLessThan(0.65) // …but never normalized to the top
    const { gateDb, ceilDb } = m.trackers
    expect(ceilDb - gateDb).toBeGreaterThanOrEqual(CEIL_MIN_SPAN_DB - 1e-9)
  })

  it('held speech cannot drag the gate up into the speech band (floor rise clamp)', () => {
    const m = new AmplitudeMapper()
    run(m, lin(-12), 60) // a minute of continuous loud speech, no pauses
    const { gateDb } = m.trackers
    expect(gateDb).toBeLessThanOrEqual(GATE_HI_DB) // gate stays below real speech
    // Quiet speech right after is still visible.
    expect(run(m, lin(-30), 0.4)).toBeGreaterThan(0.1)
  })

  it('adapts across mic gain: the same speech/floor RELATIONSHIP maps similarly on a hot vs quiet mic', () => {
    // Same scene, recorded 12dB apart (mic gain), after the trackers settle.
    const quietMic = new AmplitudeMapper()
    run(quietMic, lin(-62), 2)
    run(quietMic, lin(-26), 8)
    const hotMic = new AmplitudeMapper()
    run(hotMic, lin(-50), 2)
    run(hotMic, lin(-14), 8)
    const outQuiet = run(quietMic, lin(-26), 0.5)
    const outHot = run(hotMic, lin(-14), 0.5)
    // Bounded adaptation can't fully erase a 12dB gain difference (by design —
    // full AGC is what caused the old "quiet input maxed the bars" era), but
    // both must clearly read as normal speech around the upper half. (0.6 →
    // 0.55 with the 2026-07-18 top-end trim: the extra peak headroom scales the
    // whole curve down a few percent; the quiet-mic scenario sits right at the
    // min-span clamp so it feels the full shift.)
    expect(Math.abs(outQuiet - outHot)).toBeLessThan(0.25)
    expect(outQuiet).toBeGreaterThan(0.55)
    expect(outHot).toBeGreaterThan(0.55)
  })

  it('digital-silence floor clamps the gate at the low end of the band', () => {
    const m = new AmplitudeMapper()
    run(m, lin(-79), 8) // near-digital silence (still above NO_SIGNAL)
    expect(m.trackers.gateDb).toBeCloseTo(GATE_LO_DB, 5)
  })
})

describe('AmplitudeMapper determinism / rate independence', () => {
  it('is deterministic for a given (raw, dt) script', () => {
    const script = [0.001, 0.05, 0.2, 0.1, 0.005, 0.3, 0]
    const a = new AmplitudeMapper()
    const b = new AmplitudeMapper()
    const outA = script.map((r) => a.step(r, DT))
    const outB = script.map((r) => b.step(r, DT))
    expect(outA).toEqual(outB)
  })

  it('60fps and 30fps stepping converge to the same settled level (constant-rate rule)', () => {
    const at30 = new AmplitudeMapper()
    const at60 = new AmplitudeMapper()
    for (let t = 0; t < 5; t += 1 / 30) at30.step(0.15, 1 / 30)
    for (let t = 0; t < 5; t += 1 / 60) at60.step(0.15, 1 / 60)
    expect(at30.step(0.15, 1 / 30)).toBeCloseTo(at60.step(0.15, 1 / 60), 2)
  })
})
