import { describe, it, expect } from 'vitest'
import { createMusicGate, MUSIC_WINDOW_SAMPLES } from './musicGate'
import type { SpeechMusicClassifier, SpeechMusicVerdict } from './loopbackClassifier'

/** Scripted classifier: returns the queued verdicts in order, then 'unknown'. */
function scripted(verdicts: SpeechMusicVerdict[]): SpeechMusicClassifier & { calls: number } {
  const c = {
    calls: 0,
    classify(): SpeechMusicVerdict {
      return verdicts[c.calls++] ?? 'unknown'
    }
  }
  return c
}

const chunk = (n: number): Int16Array => new Int16Array(n).fill(1000)

describe('musicGate (loopback speech/music gating)', () => {
  it('passes everything before the first window completes (fail-open warmup)', () => {
    const gate = createMusicGate(scripted(['music']))
    const out = gate.push(chunk(4096))
    expect(out).not.toBeNull()
    expect(gate.verdict()).toBe('unknown') // not enough audio to classify yet
  })

  it('classifies once per full window and closes on music', () => {
    const c = scripted(['music'])
    const gate = createMusicGate(c)
    // 3 chunks < 1 window: all pass, no classification.
    gate.push(chunk(8000))
    expect(c.calls).toBe(0)
    // Completing the window classifies → music → THIS chunk is dropped.
    const out = gate.push(chunk(8000))
    expect(c.calls).toBe(1)
    expect(out).toBeNull()
    expect(gate.verdict()).toBe('music')
    // Subsequent audio stays dropped while the verdict is music.
    expect(gate.push(chunk(4096))).toBeNull()
  })

  it('reopens when a later window says speech', () => {
    const gate = createMusicGate(scripted(['music', 'speech']))
    gate.push(chunk(MUSIC_WINDOW_SAMPLES)) // → music (closed)
    expect(gate.push(chunk(1000))).toBeNull()
    // Keep feeding while closed — classification still runs on the buffered
    // audio, so speech returning reopens the gate.
    const out = gate.push(chunk(MUSIC_WINDOW_SAMPLES))
    expect(gate.verdict()).toBe('speech')
    expect(out).not.toBeNull()
  })

  it('a chunk larger than several windows classifies each window', () => {
    const c = scripted(['speech', 'speech', 'music'])
    const gate = createMusicGate(c)
    gate.push(chunk(MUSIC_WINDOW_SAMPLES * 3))
    expect(c.calls).toBe(3)
    expect(gate.verdict()).toBe('music')
  })

  it('unknown verdicts always pass (never drop on uncertainty)', () => {
    const gate = createMusicGate(scripted(['unknown', 'unknown']))
    expect(gate.push(chunk(MUSIC_WINDOW_SAMPLES))).not.toBeNull()
    expect(gate.push(chunk(MUSIC_WINDOW_SAMPLES))).not.toBeNull()
  })

  it('a throwing classifier fails open', () => {
    const gate = createMusicGate({
      classify(): SpeechMusicVerdict {
        throw new Error('model exploded')
      }
    })
    expect(gate.push(chunk(MUSIC_WINDOW_SAMPLES))).not.toBeNull()
    expect(gate.verdict()).toBe('unknown')
  })

  it('setClassifier hot-swaps mid-stream (passthrough → yamnet pattern)', () => {
    const gate = createMusicGate(scripted(['speech']))
    gate.push(chunk(MUSIC_WINDOW_SAMPLES))
    expect(gate.verdict()).toBe('speech')
    gate.setClassifier(scripted(['music']))
    expect(gate.push(chunk(MUSIC_WINDOW_SAMPLES))).toBeNull()
    expect(gate.verdict()).toBe('music')
  })
})
