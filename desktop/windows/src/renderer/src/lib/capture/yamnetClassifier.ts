// MediaPipe AudioClassifier (YAMNet) implementation of SpeechMusicClassifier.
// Assets are SELF-HOSTED under /vad/ (staged by scripts/copy-vad-assets.mjs:
// the tasks-audio SIMD wasm pair + the sha256-pinned yamnet.tflite) — no CDN,
// works offline, same policy as the Silero VAD assets.
//
// One classifier per process (the model is ~4MB and the graph is reusable);
// createYamnetClassifier() is memoized. Failures reject — the caller
// (loopbackMusicFilter) records the fallback and stays on passthrough.
import { AudioClassifier, FilesetResolver } from '@mediapipe/tasks-audio'
import { verdictFromLabel, type SpeechMusicClassifier } from './loopbackClassifier'

const ASSET_BASE = '/vad'
const SAMPLE_RATE = 16000

let shared: Promise<SpeechMusicClassifier> | null = null

async function create(): Promise<SpeechMusicClassifier> {
  const fileset = await FilesetResolver.forAudioTasks(ASSET_BASE)
  const classifier = await AudioClassifier.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: `${ASSET_BASE}/yamnet.tflite` },
    maxResults: 1
  })
  return {
    classify(win: Int16Array) {
      // MediaPipe expects float32 in [-1, 1]; it reblocks to YAMNet's 0.975s
      // internally and returns one result per model frame.
      const f32 = new Float32Array(win.length)
      for (let i = 0; i < win.length; i++) f32[i] = win[i] / 32768
      const results = classifier.classify(f32, SAMPLE_RATE)
      const top = results[0]?.classifications[0]?.categories[0]
      if (!top) return 'unknown'
      return verdictFromLabel(top.categoryName, top.score)
    }
  }
}

/** Shared YAMNet classifier (memoized; a failed load is retried on next call). */
export function createYamnetClassifier(): Promise<SpeechMusicClassifier> {
  if (!shared) {
    shared = create().catch((e) => {
      shared = null // allow a later retry (e.g. transient asset 404 in dev)
      throw e
    })
  }
  return shared
}
