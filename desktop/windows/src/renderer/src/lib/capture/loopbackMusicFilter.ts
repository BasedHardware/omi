// Impure glue between the pure music gate and the YAMNet classifier, used by
// AudioSessionHost on the LOOPBACK lane only. Starts fail-open (passthrough
// classifier) and hot-swaps YAMNet in once it loads; a load failure records the
// bounded fallback event (same shape as the VAD gate's) and stays passthrough —
// audio must never be lost to a classifier problem.
import { passThroughClassifier, type SpeechMusicVerdict } from './loopbackClassifier'
import { createMusicGate } from './musicGate'
import { createYamnetClassifier } from './yamnetClassifier'
import { trackEvent } from '../analytics'

export type LoopbackMusicFilter = {
  push: (pcm: Int16Array) => void
  stop: () => void
  /** Current gate verdict (test/telemetry observability). */
  verdict: () => SpeechMusicVerdict
}

export function createLoopbackMusicFilter(
  onOut: (pcm: Int16Array) => void
): LoopbackMusicFilter {
  const gate = createMusicGate(passThroughClassifier)
  let stopped = false

  createYamnetClassifier()
    .then((c) => {
      if (!stopped) gate.setClassifier(c)
    })
    .catch((e) => {
      if (stopped) return
      console.warn('[loopback-classifier] yamnet unavailable — passthrough:', (e as Error).message)
      trackEvent('fallback_triggered', {
        component: 'loopback_classifier',
        from: 'yamnet',
        to: 'passthrough',
        reason: 'model_load_failed',
        outcome: 'degraded'
      })
    })

  return {
    push: (pcm: Int16Array): void => {
      const out = gate.push(pcm)
      if (out) onOut(out)
    },
    stop: (): void => {
      stopped = true
    },
    verdict: () => gate.verdict()
  }
}
