import { describe, it, expect } from 'vitest'
import { voicedStats, gateDecision } from './gate'
import {
  MIN_TOTAL_AUDIO_SEC,
  MIN_VOICED_SEC,
  VOICED_RMS_THRESHOLD,
  VOICED_FRAME_SAMPLES
} from './constants'

const SR = 16000

function zeros(ms: number): Int16Array {
  return new Int16Array(Math.round((ms / 1000) * SR))
}

function sine(ms: number, amplitude: number, freq = 440): Int16Array {
  const n = Math.round((ms / 1000) * SR)
  const out = new Int16Array(n)
  for (let i = 0; i < n; i++) out[i] = Math.round(amplitude * Math.sin((2 * Math.PI * freq * i) / SR))
  return out
}

function concat(...parts: Int16Array[]): Int16Array {
  const out = new Int16Array(parts.reduce((n, p) => n + p.length, 0))
  let off = 0
  for (const p of parts) {
    out.set(p, off)
    off += p.length
  }
  return out
}

describe('voicedStats', () => {
  it('measures silence as zero voiced', () => {
    const s = voicedStats(zeros(1000))
    expect(s.totalSec).toBeCloseTo(1.0, 3)
    expect(s.voicedSec).toBe(0)
  })

  it('measures a loud sine as fully voiced', () => {
    const s = voicedStats(sine(1000, 8000))
    expect(s.voicedSec).toBeGreaterThan(0.95)
    expect(s.voicedSec).toBeLessThanOrEqual(1.0)
  })

  it('does not count low-level noise as voiced (RMS below threshold)', () => {
    // sine RMS = amplitude/√2; amplitude 100 → RMS ≈ 71, far under 300.
    expect(voicedStats(sine(1000, 100)).voicedSec).toBe(0)
  })

  it('applies the RMS threshold with >= semantics at the boundary', () => {
    // amplitude a → RMS a/√2. 430/√2 ≈ 304 (voiced); 400/√2 ≈ 283 (not).
    expect(voicedStats(sine(1000, 430)).voicedSec).toBeGreaterThan(0.9)
    expect(voicedStats(sine(1000, 400)).voicedSec).toBe(0)
  })

  it('measures voiced islands inside silence', () => {
    // 100ms of speech embedded in 1s of silence (frame-aligned).
    const s = voicedStats(concat(zeros(400), sine(100, 8000), zeros(500)))
    expect(s.voicedSec).toBeCloseTo(0.1, 2)
    expect(s.totalSec).toBeCloseTo(1.0, 3)
  })

  it('handles a trailing partial frame without throwing', () => {
    const pcm = new Int16Array(VOICED_FRAME_SAMPLES + 7)
    expect(() => voicedStats(pcm)).not.toThrow()
    expect(voicedStats(pcm).totalSec).toBeCloseTo(pcm.length / SR, 6)
  })

  it('handles an empty buffer', () => {
    const s = voicedStats(new Int16Array(0))
    expect(s.totalSec).toBe(0)
    expect(s.voicedSec).toBe(0)
  })

  it('gates a full 4.5-minute buffer within the perf budget', () => {
    voicedStats(sine(1000, 3000)) // JIT warm-up so the measurement isn't cold-start
    const pcm = sine(4.5 * 60 * 1000, 3000)
    const t0 = performance.now()
    voicedStats(pcm)
    const ms = performance.now() - t0
    // Tens of ms warm in practice for the 4.5-MINUTE worst case (a typical 2s
    // hold is ~1ms). The budget exists to catch order-of-magnitude regressions,
    // sized generously so parallel-CI load can't flake it.
    console.log(`[gate] 4.5min voicedStats: ${ms.toFixed(1)}ms`)
    expect(ms).toBeLessThan(400)
  })
})

describe('gateDecision', () => {
  it('flags a capture shorter than the minimum as too-short regardless of voicing', () => {
    expect(
      gateDecision({ totalSec: MIN_TOTAL_AUDIO_SEC - 0.01, voicedSec: MIN_TOTAL_AUDIO_SEC - 0.01, peak: 8000 })
    ).toBe('too-short')
  })

  it('accepts exactly the minimum total duration', () => {
    expect(gateDecision({ totalSec: MIN_TOTAL_AUDIO_SEC, voicedSec: MIN_VOICED_SEC, peak: 8000 })).toBe('ok')
  })

  it('discards a long-but-silent hold silently', () => {
    expect(gateDecision({ totalSec: 2.0, voicedSec: MIN_VOICED_SEC - 0.01, peak: 200 })).toBe('silent')
  })

  it('accepts exactly the minimum voiced duration', () => {
    expect(gateDecision({ totalSec: 1.0, voicedSec: MIN_VOICED_SEC, peak: 8000 })).toBe('ok')
  })

  it('measures peak so a dead input can be told from a quiet room', () => {
    expect(voicedStats(zeros(1000)).peak).toBe(0)
    expect(voicedStats(sine(1000, 8000)).peak).toBeGreaterThan(7500)
  })

  it('distinguishes dead-mic (flat-line) from silent (quiet room)', () => {
    expect(gateDecision({ totalSec: 2.0, voicedSec: 0, peak: 0 })).toBe('dead-mic')
    expect(gateDecision({ totalSec: 2.0, voicedSec: 0, peak: 200 })).toBe('silent')
  })

  it('end-to-end: quiet speech below the RMS threshold is discarded, loud is kept', () => {
    // Mirrors the generated speech-quiet fixture (×0.05 attenuation → RMS ~142).
    const quiet = sine(1000, 200)
    const loud = sine(1000, 3000)
    expect(gateDecision(voicedStats(quiet))).toBe('silent')
    expect(gateDecision(voicedStats(loud))).toBe('ok')
  })

  it('threshold constants are the macOS-parity values tests were written against', () => {
    // If these change, re-verify against macOS PushToTalkManager and update the
    // fixture generator's mirrored literals.
    expect(MIN_TOTAL_AUDIO_SEC).toBe(0.35)
    expect(MIN_VOICED_SEC).toBe(0.2)
    expect(VOICED_RMS_THRESHOLD).toBe(300)
    expect(VOICED_FRAME_SAMPLES).toBe(320)
  })
})
