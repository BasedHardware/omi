// Pure music gate for the loopback lane: sits DOWNSTREAM of the VAD gate (its
// input is voiced-only audio, so classification runs "only while the VAD gate
// is open" by construction). Accumulates ~1s windows, asks the classifier, and
// drops frames while the current verdict is `music`.
//
// Deterministic and classifier-agnostic — hermetic tests stub the classifier
// (musicGate.test.ts); the real YAMNet implementation is wired by
// AudioSessionHost via yamnetClassifier.ts.
import {
  verdictIsCapturable,
  type SpeechMusicClassifier,
  type SpeechMusicVerdict
} from './loopbackClassifier'

export type MusicGate = {
  /** Feed one voiced chunk; returns the chunk to forward, or null while the
   *  gate is closed on music. */
  push: (pcm: Int16Array) => Int16Array | null
  /** Current verdict (for tests/telemetry). */
  verdict: () => SpeechMusicVerdict
  /** Swap the classifier once the real model loads (fail-open until then). */
  setClassifier: (c: SpeechMusicClassifier) => void
}

// YAMNet's native input is 0.975s @16kHz; a 1s window keeps the reblocking
// trivial and matches the "~1s windows" spec.
export const MUSIC_WINDOW_SAMPLES = 16000

export function createMusicGate(
  initial: SpeechMusicClassifier,
  windowSamples = MUSIC_WINDOW_SAMPLES
): MusicGate {
  let classifier = initial
  let verdict: SpeechMusicVerdict = 'unknown'
  // One reusable window buffer (hot path: ~4 pushes/s while voiced). Safe to
  // reuse because classify() is synchronous and must not retain its input.
  const buf = new Int16Array(windowSamples)
  let filled = 0

  const classifyWindow = (win: Int16Array): void => {
    try {
      verdict = classifier.classify(win)
    } catch {
      verdict = 'unknown' // fail-open: a classifier crash must never drop audio
    }
  }

  return {
    push(pcm: Int16Array): Int16Array | null {
      // Accumulate into fixed windows; a large chunk can complete several.
      let offset = 0
      while (offset < pcm.length) {
        const take = Math.min(windowSamples - filled, pcm.length - offset)
        buf.set(pcm.subarray(offset, offset + take), filled)
        filled += take
        offset += take
        if (filled === windowSamples) {
          classifyWindow(buf)
          filled = 0
        }
      }
      // The verdict (updated at 1s granularity) gates the CURRENT chunk.
      return verdictIsCapturable(verdict) ? pcm : null
    },
    verdict: () => verdict,
    setClassifier: (c: SpeechMusicClassifier): void => {
      classifier = c
    }
  }
}
