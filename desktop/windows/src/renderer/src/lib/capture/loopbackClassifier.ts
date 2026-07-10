// Speech-vs-music classification seam for the SYSTEM-AUDIO (loopback) lane.
//
// DECIDED (v1): no on-device audio classifier. A YAMNet/MediaPipe model is ~4MB
// of extra bundle plus a second inference graph, and in v1 loopback capture only
// runs inside an EXPLICIT user-started session — the user already declared intent,
// so filtering out music/media there is low-value. This module is the seam that
// keeps that decision reversible.
//
// PHASE 5 UPGRADE PATH (ambient auto-capture): when the app starts auto-capturing
// system audio without an explicit session, we DO need to skip music/video/media so
// we don't transcribe a movie. Swap `passThroughClassifier` for a MediaPipe Audio
// Classifier (YAMNet) implementation of `SpeechMusicClassifier` — load the .tflite
// as a /vad/-style staged asset, run it on the same 16kHz windows, and map its
// AudioSet labels to speech/music/unknown. The gate already understands the verdict
// via `verdictIsCapturable`, so only this file changes.

export type SpeechMusicVerdict = 'speech' | 'music' | 'unknown'

export interface SpeechMusicClassifier {
  /** Classify a 16kHz mono PCM window. `unknown` when undecided (fail-open). */
  classify(win: Int16Array): SpeechMusicVerdict
}

/** v1 default: classify everything as speech (capture-everything, fail-open). */
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
