// The real capture engine behind capture/engine.ts. Exposes the EXACT contract the
// capture hosts (AudioSessionHost) already call — a synchronous createPcmPipeline
// and a functional createVadGate({onVoiced,onStatus}) — implemented over Agent B's
// modules, so no host changes are needed at integration.
//
// Design (see vadModel.ts): ONE audio graph. The pipeline's own 16kHz Int16 frames
// feed BOTH the WebSocket AND the Silero detector — no second getUserMedia, no
// second AudioContext. The mic is released the moment the pipeline stops (privacy),
// while the InferenceSession persists for the whole process.
import { makePipelineHandle } from './pipelineHandle'
import { createPcmPipeline as createWorkletPipeline } from './pcmPipeline'
import { VadGate as PureVadGate } from './vadGate'
import { createSileroDetector, SILERO_FRAME_SAMPLES, type SileroDetector } from './vadModel'
import { SpeechHysteresis, Float32Reblocker } from './speechTicker'
import { classifyVadFailure } from './vadFallback'
import { trackEvent } from '../analytics'

// ── Contract shared with the capture hosts (mirrors the retired enginesShim) ──────
export type PcmPipeline = { stop: () => void }
export type VadMode = 'gated' | 'fallback'
export type VadGateConfig = {
  /** Audio that passed the gate (or ALL audio while falling open) — forward to WS. */
  onVoiced: (pcm: Int16Array) => void
  /** Whether the gate is actually gating or failing open, for telemetry/UI. */
  onStatus?: (mode: VadMode, reason?: string) => void
}
export type VadGate = { push: (pcm: Int16Array) => void; stop: () => void }

// Pre-speech pad / redemption hangover — sized to absorb detection latency so the
// gate never clips a word's onset or tail. (vad-web v5 defaults are ~ms-scale.)
const PRE_SPEECH_PAD_MS = 400
const REDEMPTION_MS = 600

/**
 * Convert a live MediaStream to 16kHz mono Int16 frames, calling onChunk per frame.
 * SYNCHRONOUS handle over the async worklet setup; stop() releases the mic (stops
 * the stream tracks) even if it races ahead of setup.
 */
export function createPcmPipeline(
  stream: MediaStream,
  onChunk: (pcm: Int16Array) => void
): PcmPipeline {
  return makePipelineHandle(
    stream,
    createWorkletPipeline(stream, onChunk, (reason) => {
      // The pipeline degraded to ScriptProcessor (audio still flows) — same
      // bounded fallback shape as the VAD gate's, different component.
      trackEvent('fallback_triggered', {
        component: 'pcm_pipeline',
        from: 'worklet',
        to: 'script_processor',
        reason,
        outcome: 'degraded'
      })
    })
  )
}

/**
 * Create a Silero-backed VAD gate. Frames pushed in are gated to voiced audio only
 * and forwarded via onVoiced. The detector runs on the SAME frames (no second mic).
 * Fails OPEN — during model warm-up and on any init/runtime error, every frame
 * passes through so audio is never lost — and reports the transition once.
 */
export function createVadGate(config: VadGateConfig): VadGate {
  const gate = new PureVadGate({
    preSpeechPadMs: PRE_SPEECH_PAD_MS,
    redemptionMs: REDEMPTION_MS,
    mode: 'gated'
  })
  const reblock = new Float32Reblocker(SILERO_FRAME_SAMPLES)
  const hysteresis = new SpeechHysteresis()

  let detector: SileroDetector | null = null
  let stopped = false
  let failedOpen = false

  const emit = (chunks: Int16Array[]): void => {
    for (const c of chunks) config.onVoiced(c)
  }

  const failOpen = (reason: string): void => {
    if (failedOpen || stopped) return
    failedOpen = true
    config.onStatus?.('fallback', reason)
    trackEvent('fallback_triggered', {
      component: 'vad_gate',
      from: 'gated',
      to: 'passthrough',
      reason,
      outcome: 'degraded'
    })
  }

  // Load the detector (shared session, created once per process). A failure falls
  // open; success flips the gate live.
  createSileroDetector()
    .then((d) => {
      if (stopped || failedOpen) return
      detector = d
      config.onStatus?.('gated')
    })
    .catch((e) => failOpen(classifyVadFailure((e as Error)?.message || '')))

  const runFrame = async (frame: Float32Array): Promise<void> => {
    const d = detector
    if (!d || stopped || failedOpen) return
    let prob: number
    try {
      prob = await d.process(frame)
    } catch {
      // Mid-session model error → fail open for the rest of this session (req 4:
      // audio flow must survive). Future frames take the passthrough branch below.
      failOpen('other')
      return
    }
    if (stopped || failedOpen) return
    const t = hysteresis.feed(prob)
    if (t === 'start') emit(gate.push({ type: 'speech', active: true }))
    else if (t === 'end') emit(gate.push({ type: 'speech', active: false }))
  }

  const push = (pcm: Int16Array): void => {
    if (stopped) return
    if (failedOpen || !detector) {
      // Fallback OR still warming up: pass audio straight through (never gate-drop
      // while we can't classify). No gate buffering, no transfer hazard.
      config.onVoiced(pcm)
      return
    }
    // ORDER MATTERS: copy samples for the detector BEFORE the gate can emit this
    // frame — a gated emit hands pcm.buffer to listenFeed, which TRANSFERS (detaches)
    // it. Reblock reads the samples first, so the detector never sees a detached buffer.
    for (const frame of reblock.push(pcm)) void runFrame(frame)
    emit(gate.push({ type: 'frame', pcm }))
  }

  return {
    push,
    // Only per-session state is dropped; the shared InferenceSession persists.
    stop: (): void => {
      stopped = true
    }
  }
}
