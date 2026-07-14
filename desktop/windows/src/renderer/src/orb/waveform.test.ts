import { describe, it, expect } from 'vitest'
import {
  WAVE,
  WAVE_MAX_SLOTS,
  WAVE_LEVEL_CEIL,
  WAVE_NOISE_GATE,
  waveHalfWidth,
  slotCountForAspect,
  shapeBarLevel,
  waveBars,
  historyPush,
  historySlots,
  stepWaveLevels
} from './waveform'
import { RING_DOT_RENDER_RADIUS } from './choreography'

describe('shapeBarLevel (gated sensitivity curve, calibrated to real mic)', () => {
  // Reference points are the user's MEASURED live orbLevel distribution
  // (2026-07-12, ~956 samples = (rms/255)·2.2): room silence p50 0.49 / p95 0.65
  // / max 0.75; normal speech p50 0.98 / p95 1.32 / max 1.38.
  const SILENCE_P50 = 0.49
  const SILENCE_P95 = 0.65
  const SPEECH_P50 = 0.98
  const SPEECH_MAX = 1.38

  it('gates the ambient floor to a resting dot (level 0)', () => {
    expect(shapeBarLevel(0)).toBe(0)
    expect(shapeBarLevel(-5)).toBe(0) // negatives clamp to silence
    // The whole measured room-silence band must read as a rest dot, not tall
    // bars — this is the user's core complaint the gate fixes.
    expect(shapeBarLevel(SILENCE_P50)).toBe(0)
    expect(shapeBarLevel(SILENCE_P95)).toBe(0)
    expect(shapeBarLevel(WAVE_NOISE_GATE)).toBe(0)
    // Gate sits between the silence ceiling and speech onset.
    expect(WAVE_NOISE_GATE).toBeGreaterThanOrEqual(SILENCE_P95)
    expect(WAVE_NOISE_GATE).toBeLessThan(SPEECH_P50)
  })

  it('has a soft onset just above the gate so quiet speech still registers', () => {
    const justAbove = shapeBarLevel(WAVE_NOISE_GATE + 0.05)
    expect(justAbove).toBeGreaterThan(0) // registers
    expect(justAbove).toBeLessThan(0.25) // but small — a quiet nudge, not a jump
  })

  it('places normal speech low-mid and peaks tall-but-not-pinned (softened knee)', () => {
    // Softened 2.0 → 1.5 (user: "still getting maxed"). Normal (~0.98) sits
    // low-mid so the row lives in the middle with headroom; peaks (~1.38) read
    // tall yet leave clear room below the ceiling.
    const normal = shapeBarLevel(SPEECH_P50)
    const peak = shapeBarLevel(SPEECH_MAX)
    expect(normal).toBeGreaterThanOrEqual(0.35)
    expect(normal).toBeLessThanOrEqual(0.5)
    expect(peak).toBeGreaterThan(normal)
    expect(peak).toBeGreaterThanOrEqual(0.6)
    expect(peak).toBeLessThanOrEqual(0.75)
  })

  it('keeps headroom for HOT live input — the "still getting maxed" guard', () => {
    // The user's live speech runs hotter than the calibration sample. Even a hot
    // ~1.8 must stay clearly below the ceiling (not pin), and the absolute max
    // orbLevel (2.2 = (255/255)·2.2) still leaves a sliver — bars never max out.
    expect(shapeBarLevel(1.8)).toBeLessThanOrEqual(0.86)
    expect(shapeBarLevel(2.2)).toBeLessThan(WAVE_LEVEL_CEIL)
  })

  it('is bounded below the ceiling for ANY input — never pins at max (1)', () => {
    for (const raw of [1, 2, 5, 100, 1e6]) {
      expect(shapeBarLevel(raw)).toBeLessThanOrEqual(WAVE_LEVEL_CEIL)
      expect(shapeBarLevel(raw)).toBeLessThan(1)
    }
    expect(WAVE_LEVEL_CEIL).toBeLessThan(1)
  })

  it('is monotonic non-decreasing', () => {
    let prev = -1
    for (let i = 0; i <= 40; i++) {
      const v = shapeBarLevel(i / 20)
      expect(v).toBeGreaterThanOrEqual(prev)
      prev = v
    }
  })
})

describe('slotCountForAspect', () => {
  it('gives a compact square mount a handful of slots and a wide mount many more', () => {
    const square = slotCountForAspect(1)
    const wide = slotCountForAspect(120 / 36)
    expect(square).toBeGreaterThanOrEqual(WAVE.minSlots)
    expect(square).toBeLessThanOrEqual(8) // mini visualizer
    expect(wide).toBeGreaterThan(square)
    expect(wide).toBeLessThanOrEqual(WAVE_MAX_SLOTS)
  })

  it('is monotonic in aspect and bounded on both ends', () => {
    let prev = 0
    for (const a of [0.5, 1, 1.5, 2, 3, 5, 10]) {
      const n = slotCountForAspect(a)
      expect(n).toBeGreaterThanOrEqual(prev - 1e-9) // non-decreasing
      expect(n).toBeGreaterThanOrEqual(WAVE.minSlots)
      expect(n).toBeLessThanOrEqual(WAVE_MAX_SLOTS)
      prev = n
    }
  })
})

describe('waveBars', () => {
  it('a silent slot is a small round dot (halfW == halfH, well below a bar), loud is taller', () => {
    const [silent, loud] = waveBars([0, 1], 1)
    // Rest = a circle: width == height.
    expect(silent.halfW).toBeCloseTo(silent.halfH, 9)
    // …and clearly shorter than a loud bar (the "shorten resting bars" ask).
    expect(loud.halfH).toBeGreaterThan(silent.halfH * 2)
    // Loud slot is a tall vertical bar: taller than it is wide.
    expect(loud.halfH).toBeGreaterThan(loud.halfW)
  })

  it('resting dot renders at the ring-dot radius (no crossfade pop), clamped to the bar width', () => {
    // Dot-mass regression guard. The resting waveform dot is pinned to the
    // orbiting ring dot's RENDERED radius (RING_DOT_RENDER_RADIUS) so the
    // ring↔waveform crossfade swaps like for like with no thickness pop. It is
    // clamped to the bar half-width so it can never render fatter than a speaking
    // bar. (A past change silently thinned the resting dot and the user caught it;
    // the mass is now pinned to RING_DOT_RENDER_RADIUS, itself guarded below.)

    // Wide-pitch mount (few slots → barW ≫ ring radius): NOT clamped, so the dot
    // lands exactly on the ring-dot render radius.
    const wide = waveBars([0], 1)[0]
    const barWWide = ((2 * waveHalfWidth(1)) / 1) * WAVE.barRadiusFrac
    expect(barWWide).toBeGreaterThan(RING_DOT_RENDER_RADIUS) // precondition: no clamp
    expect(wide.halfH).toBeCloseTo(RING_DOT_RENDER_RADIUS, 9)
    expect(wide.halfH).toBeLessThan(barWWide) // still a dot, not a full bar

    // Narrow-pitch mount (many slots → barW < ring radius): clamps to the bar
    // width so the dot never exceeds it.
    const narrow = waveBars(new Array(40).fill(0), 5)[0]
    const barWNarrow = ((2 * waveHalfWidth(5)) / 40) * WAVE.barRadiusFrac
    expect(barWNarrow).toBeLessThan(RING_DOT_RENDER_RADIUS) // precondition: clamp engages
    expect(narrow.halfH).toBeCloseTo(barWNarrow, 9)

    // Dot-mass floor: the ring-dot render radius (dotRadius·discRadius) must stay
    // in a comfortably-visible band — a future tweak to dotRadius/discRadius can't
    // silently thin the resting dot to a speck (user: too-thin read "way too
    // tiny") nor bloat it past a dot.
    expect(RING_DOT_RENDER_RADIUS).toBeGreaterThanOrEqual(0.08)
    expect(RING_DOT_RENDER_RADIUS).toBeLessThanOrEqual(0.12)
  })

  it('bars are evenly spaced, centered on the row, and within bounds', () => {
    const n = 12
    const bars = waveBars(
      Array.from({ length: n }, (_, i) => i / (n - 1)),
      3
    )
    expect(bars).toHaveLength(n)
    // Symmetric about x=0 (evenly spread across the row).
    const xs = bars.map((b) => b.x)
    expect(xs[0]).toBeCloseTo(-xs[xs.length - 1], 9)
    // Even pitch.
    const pitch = xs[1] - xs[0]
    for (let i = 2; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeCloseTo(pitch, 9)
    // Every bar stays within the short-axis half (y) and the row half-width (x).
    for (const b of bars) {
      expect(b.halfH).toBeLessThanOrEqual(WAVE.maxHalfExtent + 1e-9)
      expect(Math.abs(b.x) + b.halfW).toBeLessThanOrEqual(waveHalfWidth(3) + b.halfW + 1e-9)
    }
  })

  it('clamps out-of-range levels (bounded height for hot/negative input)', () => {
    const bars = waveBars([-5, 5, 100], 1)
    for (const b of bars) {
      expect(b.halfH).toBeLessThanOrEqual(WAVE.maxHalfExtent + 1e-9)
    }
    // -5 clamps to the rest dot; 5/100 clamp to the max bar height.
    expect(bars[0].halfW).toBeCloseTo(bars[0].halfH, 9) // a dot
    expect(bars[1].halfH).toBeCloseTo(WAVE.maxHalfExtent, 9)
  })

  it('returns nothing for an empty level array', () => {
    expect(waveBars([], 1)).toEqual([])
  })
})

describe('history ring buffer', () => {
  it('scrolls newest→right: the last pushed sample is the rightmost slot', () => {
    const buf = new Float32Array(WAVE_MAX_SLOTS)
    let w = 0
    for (const v of [0.1, 0.2, 0.3, 0.4]) w = historyPush(buf, w, v)
    const slots = historySlots(buf, w, 4)
    // oldest→newest (Float32 storage → compare with tolerance).
    ;[0.1, 0.2, 0.3, 0.4].forEach((v, i) => expect(slots[i]).toBeCloseTo(v, 6))
    expect(slots[slots.length - 1]).toBeCloseTo(0.4, 6) // newest is rightmost
  })

  it('wraps the ring and clamps pushed values to [0,1]', () => {
    const buf = new Float32Array(4)
    let w = 0
    for (const v of [1, 2, 3, 4, 5]) w = historyPush(buf, w, v) // 5 pushes into a 4-ring
    // All clamped to 1; the ring holds the last 4 (all 1s here).
    expect(historySlots(buf, w, 4)).toEqual([1, 1, 1, 1])
    // Negative clamps to 0.
    w = historyPush(buf, w, -3)
    expect(historySlots(buf, w, 1)).toEqual([0])
  })

  it('an unfilled ring reads as silence (zeros), not garbage', () => {
    const buf = new Float32Array(WAVE_MAX_SLOTS)
    expect(historySlots(buf, 0, 6)).toEqual([0, 0, 0, 0, 0, 0])
  })
})

describe('stepWaveLevels', () => {
  it('eases the display toward the target (no single-frame snap) and converges', () => {
    const display = new Float32Array([0, 0, 0])
    const target = [1, 0.5, 0]
    stepWaveLevels(display, target, 1 / 60)
    // Moved toward the target but not all the way in one frame.
    expect(display[0]).toBeGreaterThan(0)
    expect(display[0]).toBeLessThan(1)
    // Converges after enough steps.
    for (let i = 0; i < 200; i++) stepWaveLevels(display, target, 1 / 60)
    expect(display[0]).toBeCloseTo(1, 3)
    expect(display[1]).toBeCloseTo(0.5, 3)
    expect(display[2]).toBeCloseTo(0, 3)
  })
})
