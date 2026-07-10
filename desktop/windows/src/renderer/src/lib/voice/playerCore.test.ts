import { describe, it, expect } from 'vitest'
import { PlayerCore, pcm16BytesToFloat32 } from './playerCore'

const CUSHION = 100

function samples(n: number, value = 0.5): Float32Array {
  return new Float32Array(n).fill(value)
}

describe('PlayerCore jitter buffer', () => {
  it('does not start until the cushion is reached (silence out)', () => {
    const p = new PlayerCore(CUSHION)
    p.enqueue(samples(CUSHION - 1))
    const out = new Float32Array(32)
    const r = p.pull(out)
    expect(r.wroteAudio).toBe(false)
    expect(r.drained).toBe(false)
    expect(out.every((v) => v === 0)).toBe(true)
    expect(p.playing).toBe(false)
  })

  it('starts once the cushion fills, then plays real samples', () => {
    const p = new PlayerCore(CUSHION)
    p.enqueue(samples(CUSHION))
    expect(p.playing).toBe(true)
    const out = new Float32Array(32)
    const r = p.pull(out)
    expect(r.wroteAudio).toBe(true)
    expect(out[0]).toBeCloseTo(0.5)
  })

  it('crosses chunk boundaries seamlessly', () => {
    const p = new PlayerCore(4)
    p.enqueue(new Float32Array([1, 2, 3]))
    p.enqueue(new Float32Array([4, 5]))
    const out = new Float32Array(5)
    p.pull(out)
    expect(Array.from(out)).toEqual([1, 2, 3, 4, 5])
  })

  it('reports drained exactly once per burst, zero-padding the shortfall', () => {
    const p = new PlayerCore(4)
    p.enqueue(samples(6, 0.25))
    const out = new Float32Array(8)
    const r1 = p.pull(out)
    expect(r1.wroteAudio).toBe(true)
    expect(r1.drained).toBe(true)
    expect(out[5]).toBeCloseTo(0.25)
    expect(out[6]).toBe(0) // padded
    // Next frame: burst over, silent, no second drain event.
    const r2 = p.pull(out)
    expect(r2.wroteAudio).toBe(false)
    expect(r2.drained).toBe(false)
  })

  it('re-cushions after a full drain (next burst waits again)', () => {
    const p = new PlayerCore(CUSHION)
    p.enqueue(samples(CUSHION))
    p.pull(new Float32Array(CUSHION)) // drain the burst fully
    expect(p.playing).toBe(false)
    p.enqueue(samples(CUSHION - 1))
    expect(p.playing).toBe(false) // below cushion — not started yet
    p.enqueue(samples(1))
    expect(p.playing).toBe(true)
  })

  it('keeps playing a mid-stream dip without re-cushioning (only a full drain stops)', () => {
    const p = new PlayerCore(CUSHION)
    p.enqueue(samples(CUSHION))
    p.pull(new Float32Array(CUSHION - 10)) // dip to 10 queued — below cushion
    expect(p.playing).toBe(true)
    p.enqueue(samples(5))
    const r = p.pull(new Float32Array(15)) // exactly drains
    expect(r.wroteAudio).toBe(true)
    expect(r.drained).toBe(true)
  })

  it('flush() plays a sub-cushion end-of-turn tail instead of withholding it', () => {
    const p = new PlayerCore(CUSHION)
    p.enqueue(samples(30, 0.25)) // below cushion — would never start on its own
    expect(p.playing).toBe(false)
    p.flush() // turnComplete: no more audio is coming
    expect(p.playing).toBe(true)
    const out = new Float32Array(30)
    const r = p.pull(out)
    expect(r.wroteAudio).toBe(true)
    expect(r.drained).toBe(true)
    expect(out[0]).toBeCloseTo(0.25)
    // flush with nothing queued is a no-op (must not start a silent burst).
    p.flush()
    expect(p.playing).toBe(false)
  })

  it('clear() drops everything instantly (barge-in) and reports whether it was active', () => {
    const p = new PlayerCore(4)
    p.enqueue(samples(50))
    expect(p.clear()).toBe(true)
    expect(p.queuedSamples).toBe(0)
    const out = new Float32Array(8)
    const r = p.pull(out)
    expect(r.wroteAudio).toBe(false)
    expect(out.every((v) => v === 0)).toBe(true)
    // Clearing an already-empty player is not "active".
    expect(p.clear()).toBe(false)
  })

  it('cushion math: 150ms at 24kHz is 3600 samples', () => {
    // Guard the constant relationship the player wrapper relies on.
    expect(Math.round((150 / 1000) * 24000)).toBe(3600)
  })
})

describe('pcm16BytesToFloat32', () => {
  it('decodes little-endian int16 to [-1, 1)', () => {
    const bytes = new Uint8Array(6)
    const view = new DataView(bytes.buffer)
    view.setInt16(0, 0, true)
    view.setInt16(2, 16384, true)
    view.setInt16(4, -32768, true)
    const f = pcm16BytesToFloat32(bytes)
    expect(f[0]).toBe(0)
    expect(f[1]).toBeCloseTo(0.5)
    expect(f[2]).toBe(-1)
  })

  it('ignores a trailing odd byte and respects byteOffset views', () => {
    const raw = new Uint8Array(7)
    const view = new DataView(raw.buffer)
    view.setInt16(2, 16384, true) // sample at offset 2
    const windowed = new Uint8Array(raw.buffer, 2, 5) // 2 samples + 1 dangling byte
    const f = pcm16BytesToFloat32(windowed)
    expect(f.length).toBe(2)
    expect(f[0]).toBeCloseTo(0.5)
  })
})
