// Pure speech-gate reducer: given the high-quality PCM stream (4096-sample chunks
// from pcmPipeline) and a stream of VAD verdicts (from the Silero detector wired in
// captureEngine), emit only the audio around detected speech. NO onnx / Web Audio
// import — it is a deterministic
// state machine over a tick stream, so it is exhaustively unit-testable in node.
//
// Time is derived from the audio itself (sample counts at `sampleRate`), never a
// wall clock, so tests are reproducible and the gate can't drift from the audio it
// is gating:
//   - closed: incoming chunks roll through a pre-roll ring (capacity = preSpeechPadMs).
//   - speech starts: flush the pre-roll (≤ preSpeechPadMs, trimmed) and open.
//   - speech stops: stay open for a redemption hangover (≤ redemptionMs of audio),
//     so a brief dip mid-utterance doesn't clip the tail; a new speech verdict
//     during the hangover cancels the close (false-negative recovery).
//   - passthrough mode: every chunk passes (VAD verdicts ignored) — the seam for
//     PTT / explicit-capture lanes that must never gate.
import { PcmRing } from './pcmRing'

export type VadGateMode = 'gated' | 'passthrough'

/** Map the `vadGateEnabled` preference (undefined = enabled) to a gate mode.
 *  Pure + colocated with the mode type so the Settings→capture plumbing is
 *  unit-testable without importing the onnx-backed audio engine. */
export function resolveVadGateMode(vadGateEnabled: boolean | undefined): VadGateMode {
  return vadGateEnabled === false ? 'passthrough' : 'gated'
}

export type VadGateConfig = {
  /** Audio prepended before the speech-start point (from the pre-roll ring). */
  preSpeechPadMs: number
  /** How long the gate stays open after the last speech verdict. */
  redemptionMs: number
  mode: VadGateMode
  /** PCM sample rate (default 16000). */
  sampleRate?: number
}

/** One tick: either a chunk of the PCM stream to gate, or a VAD verdict update. */
export type VadTick = { type: 'frame'; pcm: Int16Array } | { type: 'speech'; active: boolean }

export class VadGate {
  private readonly rate: number
  private readonly padSamples: number
  private readonly redemptionSamples: number
  private readonly ring: PcmRing
  private open = false // currently emitting
  private speaking = false // last verdict seen
  private hangoverLeft = 0 // samples of redemption budget remaining while open+!speaking

  constructor(private readonly cfg: VadGateConfig) {
    this.rate = cfg.sampleRate ?? 16000
    this.padSamples = Math.round((cfg.preSpeechPadMs / 1000) * this.rate)
    this.redemptionSamples = Math.round((cfg.redemptionMs / 1000) * this.rate)
    this.ring = new PcmRing(this.padSamples)
  }

  /** Feed one tick; returns zero or more chunks to emit downstream, in order. */
  push(tick: VadTick): Int16Array[] {
    if (this.cfg.mode === 'passthrough') {
      return tick.type === 'frame' && tick.pcm.length > 0 ? [tick.pcm] : []
    }
    return tick.type === 'speech' ? this.setSpeech(tick.active) : this.pushFrame(tick.pcm)
  }

  /** Drop all state (session boundary). */
  reset(): void {
    this.ring.clear()
    this.open = false
    this.speaking = false
    this.hangoverLeft = 0
  }

  private setSpeech(active: boolean): Int16Array[] {
    if (active) {
      this.speaking = true
      this.hangoverLeft = this.redemptionSamples
      if (!this.open) {
        this.open = true
        // Flush the most-recent preSpeechPadMs of pre-roll (trimmed to the sample);
        // this empties the ring so the padding is never re-emitted.
        const preRoll = this.ring.drain(this.padSamples)
        return preRoll.length > 0 ? [preRoll] : []
      }
      return []
    }
    // Speech ended — keep the gate open for the redemption hangover.
    this.speaking = false
    if (this.open) this.hangoverLeft = this.redemptionSamples
    return []
  }

  private pushFrame(pcm: Int16Array): Int16Array[] {
    if (pcm.length === 0) return []
    if (this.open) {
      // Emit; if we're past speech (hangover), spend the redemption budget and close
      // once it runs out. Bounded to redemptionMs at frame granularity.
      if (!this.speaking) {
        this.hangoverLeft -= pcm.length
        if (this.hangoverLeft <= 0) {
          this.open = false
          this.hangoverLeft = 0
        }
      }
      return [pcm]
    }
    // Closed — roll through the pre-roll ring, emit nothing.
    this.ring.push(pcm)
    return []
  }
}
