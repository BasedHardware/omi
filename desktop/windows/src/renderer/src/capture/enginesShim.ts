// Thin in-Agent-A audio-engine shim. It exists ONLY so the capture hosts have a
// working pipeline + gate before Agent B's real engine (src/renderer/src/lib/
// capture/*) lands. It matches the exact signatures B is publishing, so at
// integration the orchestrator flips ./engine to re-export B's modules and this
// file is deleted with no host changes. See ./engine.ts.
//
// The shim's pipeline is a ScriptProcessor (same primitive omiListenClient/PTT
// used before this refactor); its "gate" is a pass-through that reports the
// fail-open 'fallback' mode, so audio still flows and the wiring is exercised —
// real VAD gating is B's job.
import { floatTo16BitPCM, teardownAudioGraph } from '../lib/audio'

const SAMPLE_RATE = 16000

// ── Engine interface (the contract shared with Agent B's lib/capture/*) ────────
export type PcmPipeline = { stop: () => void }
export type VadMode = 'gated' | 'fallback'
export type VadGateConfig = {
  /** Audio that passed the gate (or all audio in fallback) — forward it to the WS. */
  onVoiced: (pcm: Int16Array) => void
  /** Whether the gate is actually gating or failing open, for telemetry. */
  onStatus?: (mode: VadMode, reason?: string) => void
}
export type VadGate = { push: (pcm: Int16Array) => void; stop: () => void }

/**
 * Convert a live MediaStream to 16kHz mono Int16 PCM, calling onChunk per frame.
 * Shim implementation: a ScriptProcessor node. `stop()` tears the graph down.
 */
export function createPcmPipeline(
  stream: MediaStream,
  onChunk: (pcm: Int16Array) => void
): PcmPipeline {
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source = ctx.createMediaStreamSource(stream)
  const processor = ctx.createScriptProcessor(4096, 1, 1)
  source.connect(processor)
  processor.onaudioprocess = (e): void => onChunk(floatTo16BitPCM(e.inputBuffer.getChannelData(0)))
  processor.connect(ctx.destination)
  return {
    stop: (): void => teardownAudioGraph({ nodes: [processor, source], stream, ctx })
  }
}

/**
 * Create a VAD gate. Shim implementation: pass-through (no gating), reporting the
 * fail-open 'fallback' mode so downstream telemetry reflects that gating isn't
 * active yet. B's real gate drops non-voiced frames and reports 'gated'.
 */
export function createVadGate(config: VadGateConfig): VadGate {
  // Report fallback once, up front — the shim never actually gates.
  config.onStatus?.('fallback', 'shim-passthrough')
  return {
    push: (pcm: Int16Array): void => config.onVoiced(pcm),
    stop: (): void => {}
  }
}
