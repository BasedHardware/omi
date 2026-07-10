// Pure release-gate math for push-to-talk: decide from the captured PCM alone —
// before ANY network work — whether a hold is worth transcribing. Port of the
// macOS voicedAudioSeconds / finalize silence-gate design.
import {
  DEAD_MIC_PEAK,
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
  /** Loudest absolute sample (int16). Distinguishes a DEAD input (peak ≈ 0 —
   *  virtual cable, muted/broken device) from a merely quiet room. */
  peak: number
}

/** Measure a raw 16kHz mono PCM16 buffer: total duration + voiced duration
 *  (RMS over 20ms frames, macOS parity) + peak. A trailing partial frame is
 *  ignored for voicing but counted in totalSec/peak. */
export function voicedStats(pcm: Int16Array): AudioStats {
  const totalSec = pcm.length / 16000
  let voicedFrames = 0
  let peak = 0
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  for (let f = 0; f < frames; f++) {
    const base = f * VOICED_FRAME_SAMPLES
    let sumSq = 0
    for (let i = 0; i < VOICED_FRAME_SAMPLES; i++) {
      const s = pcm[base + i]
      sumSq += s * s
      const a = s < 0 ? -s : s
      if (a > peak) peak = a
    }
    if (Math.sqrt(sumSq / VOICED_FRAME_SAMPLES) >= VOICED_RMS_THRESHOLD) voicedFrames++
  }
  for (let i = frames * VOICED_FRAME_SAMPLES; i < pcm.length; i++) {
    const a = pcm[i] < 0 ? -pcm[i] : pcm[i]
    if (a > peak) peak = a
  }
  return { totalSec, voicedSec: (voicedFrames * VOICED_FRAME_SAMPLES) / 16000, peak }
}

export type GateDecision =
  /** Release beat the capture (fast tap): show "Hold longer to record". */
  | 'too-short'
  /** A real hold whose input is flat-lined (virtual cable, muted/broken mic):
   *  show an actionable hint — the user thinks they spoke. */
  | 'dead-mic'
  /** A real hold with no speech in a live room: discard silently — never send
   *  silence to STT (it hallucinates phrases). */
  | 'silent'
  /** Worth transcribing. */
  | 'ok'

export function gateDecision(stats: AudioStats): GateDecision {
  if (stats.totalSec < MIN_TOTAL_AUDIO_SEC) return 'too-short'
  if (stats.voicedSec < MIN_VOICED_SEC) return stats.peak < DEAD_MIC_PEAK ? 'dead-mic' : 'silent'
  return 'ok'
}
