// Pure release-gate math for push-to-talk: decide from the captured PCM alone —
// before ANY network work — whether a hold is worth transcribing. Port of the
// macOS voicedAudioSeconds / finalize silence-gate design.
import {
  MIN_TOTAL_AUDIO_SEC,
  MIN_VOICED_SEC,
  VOICED_FRAME_SAMPLES,
  VOICED_RMS_THRESHOLD
} from './constants'

export type AudioStats = {
  /** Total captured duration in seconds. */
  totalSec: number
  /** Seconds of 20ms frames whose RMS met the voiced threshold. */
  voicedSec: number
}

/** Measure a raw 16kHz mono PCM16 buffer: total duration + voiced duration
 *  (RMS over 20ms frames, macOS parity). A trailing partial frame is ignored
 *  for voicing but counted in totalSec. */
export function voicedStats(pcm: Int16Array, rmsThreshold = VOICED_RMS_THRESHOLD): AudioStats {
  const totalSec = pcm.length / 16000
  let voicedFrames = 0
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  for (let f = 0; f < frames; f++) {
    const base = f * VOICED_FRAME_SAMPLES
    let sumSq = 0
    for (let i = 0; i < VOICED_FRAME_SAMPLES; i++) {
      const s = pcm[base + i]
      sumSq += s * s
    }
    if (Math.sqrt(sumSq / VOICED_FRAME_SAMPLES) >= rmsThreshold) voicedFrames++
  }
  return { totalSec, voicedSec: (voicedFrames * VOICED_FRAME_SAMPLES) / 16000 }
}

export type GateDecision =
  /** Release beat the capture (fast tap): show "Hold longer to record". */
  | 'too-short'
  /** A real hold with no speech: discard silently — never send silence to STT
   *  (it hallucinates phrases). */
  | 'silent'
  /** Worth transcribing. */
  | 'ok'

export function gateDecision(stats: AudioStats): GateDecision {
  if (stats.totalSec < MIN_TOTAL_AUDIO_SEC) return 'too-short'
  if (stats.voicedSec < MIN_VOICED_SEC) return 'silent'
  return 'ok'
}
