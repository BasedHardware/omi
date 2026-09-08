import { describe, it, expect } from 'vitest'
import { soakVerifyCore } from './soakVerifyCore.mjs'

const HOUR = 3_600_000

/** Build a sample series: `rssMB` per point, optional per-point listen bytes. */
function series({ rssMB, bytes = [], stepMs = HOUR }) {
  return rssMB.map((mb, i) => ({
    ts: 1_000_000 + i * stepMs,
    metrics: [
      { type: 'Browser', memory: { workingSetSize: 50_000 } }, // ignored (main)
      { type: 'Tab', memory: { workingSetSize: mb * 1024 } } // renderer RSS in KB
    ],
    listen: bytes[i] !== undefined ? { 'conversation:mic': { bytes: bytes[i], chunks: i } } : {}
  }))
}

describe('soakVerifyCore', () => {
  it('passes a flat-RSS, zero-bytes idle soak', () => {
    const r = soakVerifyCore(series({ rssMB: [120, 121, 120, 122, 121], bytes: [0, 0, 0, 0, 0] }))
    expect(r.pass).toBe(true)
    expect(r.bytesDuringSilenceB).toBe(0)
    expect(Math.abs(r.rssSlopeMBperHour)).toBeLessThan(1)
    expect(r.samples).toBe(5)
  })

  it('fails when renderer RSS climbs past the slope threshold', () => {
    // 120 → 620 MB over 5h = 100 MB/h, well past 15.
    const r = soakVerifyCore(
      series({ rssMB: [120, 220, 320, 420, 520, 620], bytes: [0, 0, 0, 0, 0, 0] })
    )
    expect(r.pass).toBe(false)
    expect(r.rssSlopeMBperHour).toBeGreaterThan(15)
    expect(r.reasons.join(' ')).toMatch(/RSS slope/)
  })

  it('computes a known slope accurately', () => {
    // +10 MB/h exactly.
    const r = soakVerifyCore(series({ rssMB: [100, 110, 120, 130] }))
    expect(r.rssSlopeMBperHour).toBeCloseTo(10, 3)
    expect(r.pass).toBe(true) // 10 < 15
  })

  it('fails when bytes are fed during silence (gate leak)', () => {
    const r = soakVerifyCore(
      series({ rssMB: [120, 120, 120, 120], bytes: [0, 500_000, 1_000_000, 2_000_000] })
    )
    expect(r.pass).toBe(false)
    expect(r.bytesDuringSilenceB).toBe(2_000_000)
    expect(r.reasons.join(' ')).toMatch(/during silence/)
  })

  it('tolerates a small byte delta from VAD misfires', () => {
    const r = soakVerifyCore(series({ rssMB: [120, 120, 120], bytes: [0, 4_000, 8_000] })) // 8KB < 64KB
    expect(r.pass).toBe(true)
    expect(r.bytesDuringSilenceB).toBe(8_000)
  })

  it('refuses to pass with too few samples', () => {
    const r = soakVerifyCore(series({ rssMB: [120, 121] }))
    expect(r.pass).toBe(false)
    expect(r.reasons.join(' ')).toMatch(/need ≥/)
  })

  it('falls back to all processes when none are typed Tab', () => {
    const samples = [0, 1, 2].map((i) => ({
      ts: 1_000_000 + i * HOUR,
      metrics: [{ type: 'Utility', memory: { workingSetSize: (100 + i * 100) * 1024 } }],
      listen: {}
    }))
    const r = soakVerifyCore(samples)
    expect(r.rssSlopeMBperHour).toBeCloseTo(100, 3) // 100 MB/h from the utility process
    expect(r.pass).toBe(false)
  })
})
