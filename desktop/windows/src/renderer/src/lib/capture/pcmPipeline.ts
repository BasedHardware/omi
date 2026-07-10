// Builds an AudioWorklet capture graph over a MediaStream and delivers 16kHz
// Int16 PCM frames to onChunk — the modern replacement for the deprecated
// ScriptProcessorNode graph in lib/ptt/capture.ts / omiListenClient.ts.
//
// Preferred path: a 16kHz AudioContext, so the worklet passes samples through with
// no resampling. When a platform refuses the sampleRate hint (throws, or silently
// clamps to the hardware rate), we fall back to a native-rate context and let the
// worklet resample — pcmPipeline always tells the worklet the context's ACTUAL
// rate, so a silently-ignored hint still produces correct 16kHz output.
//
// FAIL-OPEN: if the worklet module can't load (found live: a plain `?url` import
// ships RAW TypeScript in production builds, addModule rejects, and audio died
// silently), fall back to a ScriptProcessor graph so capture keeps working, and
// report the downgrade via onFallback. `?worker&url` makes vite COMPILE the
// worklet entry and return the built asset's URL in both dev and prod.
import workletUrl from './pcmWorklet.ts?worker&url'
import { floatTo16BitPCM, linearResample } from './pcmCore'

const TARGET_RATE = 16000
const FRAME_SAMPLES = 4096

export type PcmPipeline = {
  ctx: AudioContext
  sourceNode: MediaStreamAudioSourceNode
  /** 'worklet' (preferred) or 'script-processor' (worklet module failed to load). */
  mode: 'worklet' | 'script-processor'
  /** Idempotent teardown: detach the nodes, drop the source, close the context. */
  stop: () => void
}

export async function createPcmPipeline(
  stream: MediaStream,
  onChunk: (i16: Int16Array) => void,
  onFallback?: (reason: string) => void
): Promise<PcmPipeline> {
  let ctx: AudioContext
  try {
    ctx = new AudioContext({ sampleRate: TARGET_RATE })
  } catch {
    // Some platforms reject a non-native sampleRate — take the hardware rate and
    // resample (in the worklet, or per-chunk on the fallback path).
    ctx = new AudioContext()
  }

  const sourceNode = ctx.createMediaStreamSource(stream)
  let node: AudioWorkletNode | ScriptProcessorNode
  let mode: PcmPipeline['mode'] = 'worklet'

  try {
    await ctx.audioWorklet.addModule(workletUrl)
    const worklet = new AudioWorkletNode(ctx, 'omi-pcm', {
      numberOfInputs: 1,
      numberOfOutputs: 0, // a pure sink — a 0-output worklet stays active off its input, no destination connect needed
      processorOptions: {
        inputRate: ctx.sampleRate,
        targetRate: TARGET_RATE,
        frameSamples: FRAME_SAMPLES
      }
    })
    worklet.port.onmessage = (e: MessageEvent<ArrayBuffer>): void => onChunk(new Int16Array(e.data))
    sourceNode.connect(worklet)
    node = worklet
  } catch (e) {
    // Fail open: audio capture must survive a broken worklet asset. The
    // ScriptProcessor path is deprecated but universally available.
    mode = 'script-processor'
    console.warn('[pcm-pipeline] worklet init failed — falling back to ScriptProcessor:', e)
    onFallback?.('worklet_init_failed')
    const sp = ctx.createScriptProcessor(FRAME_SAMPLES, 1, 1)
    const needsResample = ctx.sampleRate !== TARGET_RATE
    sp.onaudioprocess = (ev): void => {
      const raw = ev.inputBuffer.getChannelData(0)
      const f32 = needsResample ? linearResample(raw, ctx.sampleRate, TARGET_RATE) : raw
      onChunk(floatTo16BitPCM(f32))
    }
    sourceNode.connect(sp)
    // ScriptProcessor only fires when connected to a destination.
    sp.connect(ctx.destination)
    node = sp
  }

  let stopped = false
  const stop = (): void => {
    if (stopped) return
    stopped = true
    try {
      if ('port' in node) node.port.onmessage = null
      else node.onaudioprocess = null
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

  return { ctx, sourceNode, mode, stop }
}
