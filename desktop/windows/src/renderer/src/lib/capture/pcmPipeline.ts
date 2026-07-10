// Builds an AudioWorklet capture graph over a MediaStream and delivers 16kHz
// Int16 PCM frames to onChunk — the modern replacement for the deprecated
// ScriptProcessorNode graph in lib/ptt/capture.ts / omiListenClient.ts.
//
// Preferred path: a 16kHz AudioContext, so the worklet passes samples through with
// no resampling. When a platform refuses the sampleRate hint (throws, or silently
// clamps to the hardware rate), we fall back to a native-rate context and let the
// worklet resample — pcmPipeline always tells the worklet the context's ACTUAL
// rate, so a silently-ignored hint still produces correct 16kHz output.
import workletUrl from './pcmWorklet.ts?url'

const TARGET_RATE = 16000
const FRAME_SAMPLES = 4096

export type PcmPipeline = {
  ctx: AudioContext
  sourceNode: MediaStreamAudioSourceNode
  /** Idempotent teardown: detach the worklet, drop the source, close the context. */
  stop: () => void
}

export async function createPcmPipeline(
  stream: MediaStream,
  onChunk: (i16: Int16Array) => void
): Promise<PcmPipeline> {
  let ctx: AudioContext
  try {
    ctx = new AudioContext({ sampleRate: TARGET_RATE })
  } catch {
    // Some platforms reject a non-native sampleRate — take the hardware rate and
    // resample in the worklet instead.
    ctx = new AudioContext()
  }

  const sourceNode = ctx.createMediaStreamSource(stream)
  await ctx.audioWorklet.addModule(workletUrl)

  const node = new AudioWorkletNode(ctx, 'omi-pcm', {
    numberOfInputs: 1,
    numberOfOutputs: 0, // a pure sink — a 0-output worklet stays active off its input, no destination connect needed
    processorOptions: {
      inputRate: ctx.sampleRate,
      targetRate: TARGET_RATE,
      frameSamples: FRAME_SAMPLES
    }
  })
  node.port.onmessage = (e: MessageEvent<ArrayBuffer>): void => onChunk(new Int16Array(e.data))
  sourceNode.connect(node)

  let stopped = false
  const stop = (): void => {
    if (stopped) return
    stopped = true
    try {
      node.port.onmessage = null
    } catch {
      /* ignore */
    }
    for (const n of [node, sourceNode]) {
      try {
        n.disconnect()
      } catch {
        /* ignore */
      }
    }
    try {
      void ctx.close()
    } catch {
      /* ignore */
    }
  }

  return { ctx, sourceNode, stop }
}
