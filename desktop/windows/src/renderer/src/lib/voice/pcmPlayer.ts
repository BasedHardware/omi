// AudioWorklet-hosted jitter-buffered PCM player (Phase 6) — the Gemini Live
// 24kHz downlink path. All buffer math lives in playerCore (node-tested); the
// worklet (playerWorklet.ts) hosts one PlayerCore; this wrapper owns the
// AudioContext, the sink (setSinkId so AEC references the device actually
// playing Omi's voice), and the started/drained edges the echo gate keys off.
//
// `?worker&url` is load-bearing: a plain `?url` import ships RAW TypeScript in
// production builds and addModule rejects (Phase 2 lesson — capture died
// silently). No ScriptProcessor fallback here on purpose: the echo gate depends
// on precise drain edges, so a broken worklet asset fails the session cleanly
// (retryable error) instead of degrading into a sloppier player.
import workletUrl from './playerWorklet.ts?worker&url'
import { floatTo16BitPCM } from '../capture/pcmCore'
import { pcm16BytesToFloat32 } from './playerCore'
import { playbackLevel } from './playbackLevelBus'

export const GEMINI_OUTPUT_RATE = 24000
export const JITTER_CUSHION_MS = 150

export type VoicePlayer = {
  /** Enqueue raw 16-bit little-endian PCM bytes (the Gemini wire format). */
  enqueuePcm16(bytes: Uint8Array): void
  /** End of turn: play any queued sub-cushion tail instead of withholding it. */
  flush(): void
  /** Barge-in: drop everything buffered, immediately. */
  clear(): void
  /** Route playback to a specific output device ('' = system default). */
  setSinkId(deviceId: string): Promise<void>
  /** Idempotent teardown. */
  close(): void
}

type AudioContextWithSink = AudioContext & { setSinkId?: (id: string) => Promise<void> }

export async function createVoicePlayer(opts: {
  sampleRate?: number
  cushionMs?: number
  sinkId?: string
  /** A burst began audibly playing (echo gate: playbackStarted). */
  onStarted: () => void
  /** The burst's buffer fully drained (echo gate: start the release timer). */
  onDrained: () => void
}): Promise<VoicePlayer> {
  const rate = opts.sampleRate ?? GEMINI_OUTPUT_RATE
  const cushionMs = opts.cushionMs ?? JITTER_CUSHION_MS
  // A 24kHz context: Chromium resamples to the hardware rate at the destination,
  // so the worklet can run in wire-rate samples with no resampling of our own.
  const ctx: AudioContextWithSink = new AudioContext({ sampleRate: rate })
  if (opts.sinkId && typeof ctx.setSinkId === 'function') {
    await ctx.setSinkId(opts.sinkId).catch(() => {
      /* unknown device — stay on default */
    })
  }
  await ctx.audioWorklet.addModule(workletUrl)
  const node = new AudioWorkletNode(ctx, 'omi-voice-player', {
    numberOfInputs: 0,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: { cushionSamples: Math.round((cushionMs / 1000) * rate) }
  })
  let closed = false
  node.port.onmessage = (e: MessageEvent<{ type: string; value?: number }>): void => {
    if (closed) return
    if (e.data.type === 'started') opts.onStarted()
    else if (e.data.type === 'drained') opts.onDrained()
    // The worklet's played-audio peak (PlaybackLevelMeter) → the shared signal,
    // so the orb's speaking pose animates with the reply's real dynamics.
    else if (e.data.type === 'level' && typeof e.data.value === 'number') {
      playbackLevel.set(e.data.value)
    }
  }
  node.connect(ctx.destination)

  return {
    enqueuePcm16(bytes: Uint8Array): void {
      if (closed || bytes.byteLength < 2) return
      const f32 = pcm16BytesToFloat32(bytes)
      node.port.postMessage({ type: 'pcm', buffer: f32.buffer }, [f32.buffer])
    },
    flush(): void {
      if (!closed) node.port.postMessage({ type: 'flush' })
    },
    clear(): void {
      if (!closed) node.port.postMessage({ type: 'clear' })
    },
    async setSinkId(deviceId: string): Promise<void> {
      if (closed || typeof ctx.setSinkId !== 'function') return
      await ctx.setSinkId(deviceId)
    },
    close(): void {
      if (closed) return
      closed = true
      node.port.onmessage = null
      try {
        node.disconnect()
      } catch {
        /* ignore */
      }
      void ctx.close().catch(() => {})
    }
  }
}

// Re-export for the Gemini uplink (16kHz Int16 → base64 blobs).
export { floatTo16BitPCM }

/** Int16 PCM → base64 (chunked so large frames don't blow the arg limit). */
export function int16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength)
  let binary = ''
  const STEP = 0x8000
  for (let i = 0; i < bytes.length; i += STEP) {
    binary += String.fromCharCode(...bytes.subarray(i, i + STEP))
  }
  return btoa(binary)
}

/** base64 → bytes (the Gemini downlink inlineData payload). */
export function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
  return out
}
