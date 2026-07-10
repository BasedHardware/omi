import { describe, it, expect } from 'vitest'
import { VadGate, type VadGateConfig, type VadTick } from './vadGate'

const RATE = 16000
const FRAME = 160 // 10ms @ 16kHz

/** A frame whose samples equal their absolute stream index (so trimming/order is
 *  verifiable). Frame `i` covers samples [i*FRAME, i*FRAME+FRAME). */
function frameAt(index: number): Int16Array {
  const out = new Int16Array(FRAME)
  for (let i = 0; i < FRAME; i++) out[i] = index * FRAME + i
  return out
}

const speech = (active: boolean): VadTick => ({ type: 'speech', active })
const frame = (pcm: Int16Array): VadTick => ({ type: 'frame', pcm })

function totalSamples(chunks: Int16Array[]): number {
  return chunks.reduce((n, c) => n + c.length, 0)
}

function flatten(chunks: Int16Array[]): number[] {
  const out: number[] = []
  for (const c of chunks) out.push(...Array.from(c))
  return out
}

const gated = (over: Partial<VadGateConfig> = {}): VadGate =>
  new VadGate({ preSpeechPadMs: 100, redemptionMs: 200, mode: 'gated', sampleRate: RATE, ...over })

describe('VadGate — passthrough mode', () => {
  it('passes every frame and ignores speech verdicts', () => {
    const g = new VadGate({
      preSpeechPadMs: 100,
      redemptionMs: 200,
      mode: 'passthrough',
      sampleRate: RATE
    })
    expect(g.push(speech(false))).toEqual([])
    const f = frameAt(0)
    expect(g.push(frame(f))).toEqual([f])
    expect(g.push(speech(true))).toEqual([]) // verdict ignored, no extra output
    expect(g.push(frame(frameAt(1)))).toHaveLength(1)
  })

  it('drops empty frames', () => {
    const g = new VadGate({
      preSpeechPadMs: 100,
      redemptionMs: 200,
      mode: 'passthrough',
      sampleRate: RATE
    })
    expect(g.push(frame(new Int16Array(0)))).toEqual([])
  })
})

describe('VadGate — gated mode', () => {
  it('buffers pre-speech frames silently (nothing emitted while closed)', () => {
    const g = gated()
    for (let i = 0; i < 20; i++) expect(g.push(frame(frameAt(i)))).toEqual([])
  })

  it('flushes the pre-roll on speech start, trimmed to preSpeechPadMs and to the sample', () => {
    const g = gated() // padMs 100 → 1600 samples
    for (let i = 0; i < 20; i++) g.push(frame(frameAt(i))) // 3200 samples buffered
    const out = g.push(speech(true))
    // Most-recent 1600 samples = stream indices 1600..3199.
    expect(totalSamples(out)).toBe(1600)
    const flat = flatten(out)
    expect(flat[0]).toBe(1600)
    expect(flat[flat.length - 1]).toBe(3199)
  })

  it('never flushes more than the pre-roll capacity even after long silence', () => {
    const g = gated()
    for (let i = 0; i < 500; i++) g.push(frame(frameAt(i))) // ring eviction under load
    expect(totalSamples(g.push(speech(true)))).toBeLessThanOrEqual(1600)
  })

  it('passes frames through while speaking', () => {
    const g = gated()
    g.push(speech(true))
    const f = frameAt(0)
    expect(g.push(frame(f))).toEqual([f])
    expect(g.push(frame(frameAt(1)))).toHaveLength(1)
  })

  it('keeps the gate open for a redemption hangover of ≤ redemptionMs after speech ends', () => {
    const g = gated() // redemptionMs 200 → 3200 samples = 20 frames
    g.push(speech(true))
    g.push(frame(frameAt(0)))
    g.push(speech(false))
    let emitted = 0
    let closedAt = -1
    for (let i = 1; i <= 25; i++) {
      const out = g.push(frame(frameAt(i)))
      if (out.length > 0) emitted += FRAME
      else if (closedAt < 0) closedAt = i
    }
    // Hangover audio bounded to redemptionMs (3200 samples), at frame granularity.
    expect(emitted).toBe(3200)
    expect(closedAt).toBe(21) // frames 1..20 pass, frame 21 is the first dropped
  })

  it('a speech verdict during the hangover cancels the close (false-negative recovery)', () => {
    const g = gated()
    g.push(speech(true))
    g.push(speech(false))
    for (let i = 0; i < 5; i++) g.push(frame(frameAt(i))) // partway through hangover
    g.push(speech(true)) // re-detected
    // Still open + speaking: the next 30 frames all pass (well past the old budget).
    let passed = 0
    for (let i = 5; i < 35; i++) if (g.push(frame(frameAt(i))).length > 0) passed++
    expect(passed).toBe(30)
  })

  it('re-buffers into the pre-roll after the gate closes', () => {
    const g = gated()
    g.push(speech(true))
    g.push(speech(false))
    for (let i = 0; i < 25; i++) g.push(frame(frameAt(i))) // exhaust hangover, then buffer
    // Closed again → a fresh speech start flushes a bounded pre-roll from the new frames.
    const out = g.push(speech(true))
    expect(totalSamples(out)).toBeGreaterThan(0)
    expect(totalSamples(out)).toBeLessThanOrEqual(1600)
  })

  it('reset() drops pre-roll and returns to the closed idle state', () => {
    const g = gated()
    for (let i = 0; i < 20; i++) g.push(frame(frameAt(i)))
    g.reset()
    expect(g.push(speech(true))).toEqual([]) // nothing buffered to flush
  })
})
