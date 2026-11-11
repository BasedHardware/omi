// Speech-vs-music classification seam for the SYSTEM-AUDIO (loopback) lane.
//
// WIRED (Phase 5): AudioSessionHost's loopback lane runs a MediaPipe
// AudioClassifier (YAMNet, self-hosted /vad/yamnet.tflite — see
// yamnetClassifier.ts) over ~1s windows of VAD-gated audio; a confident
// `music` verdict closes the loopback gate (musicGate.ts) so ambient/meeting
// auto-capture never transcribes a movie or a Spotify session. The mic lane
// never classifies. `passThroughClassifier` remains the warm-up / failure
// fallback: until the model loads (or if it can't), everything passes.

export type SpeechMusicVerdict = 'speech' | 'music' | 'unknown'

export interface SpeechMusicClassifier {
  /** Classify a 16kHz mono PCM window. `unknown` when undecided (fail-open). */
  classify(win: Int16Array): SpeechMusicVerdict
}

/** Warm-up / failure default: classify everything as speech (capture-everything,
 *  fail-open). */
export const passThroughClassifier: SpeechMusicClassifier = {
  classify(): SpeechMusicVerdict {
    return 'speech'
  }
}

/** The verdict's capture semantic: only a confident `music` verdict is skipped;
 *  `speech` and `unknown` are always captured (never drop audio on uncertainty). */
export function verdictIsCapturable(verdict: SpeechMusicVerdict): boolean {
  return verdict !== 'music'
}

const SPEECH_HINTS = ['speech', 'conversation', 'narration', 'chatter', 'monologue']
const MUSIC_HINTS = ['music', 'singing', 'song', 'instrument']

/**
 * Map a YAMNet/AudioSet top-category label + score to a verdict. Pure, so the
 * mapping is hermetically testable without the model. Low-confidence results
 * are `unknown` (fail-open, per verdictIsCapturable).
 */
export function verdictFromLabel(
  label: string,
  score: number,
  threshold = 0.5
): SpeechMusicVerdict {
  if (!label || score < threshold) return 'unknown'
  const l = label.toLowerCase()
  // Speech wins ties ("Speech" and "Music" can co-occur in a scored list, but
  // here we only see the top label): never drop something that might be words.
  if (SPEECH_HINTS.some((h) => l.includes(h))) return 'speech'
  if (MUSIC_HINTS.some((h) => l.includes(h))) return 'music'
  return 'unknown'
}
