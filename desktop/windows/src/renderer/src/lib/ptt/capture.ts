// The ONE mic capture behind a push-to-talk hold. A single getUserMedia stream
// feeds three consumers (macOS AudioCaptureService parity):
//   1. the bounded local PCM buffer — the foundation every transcription lane
//      ultimately reads from,
//   2. the AnalyserNode driving the overlay waveform,
//   3. an onChunk tee for the opportunistic streaming lane.
// This replaces the old design's two separate mic streams (one for viz/VAD, one
// inside the transcription client).
import { DRAIN_MS, MAX_BUFFER_BYTES } from './constants'

export type PttCapture = {
  /** Live analyser for the waveform visualizer. */
  analyser: AnalyserNode
  /** Stop appending new audio and, after DRAIN_MS (so the in-flight
   *  ScriptProcessor window lands), release the mic and resolve the full
   *  captured buffer. Idempotent — repeat calls share one promise. */
  drain: () => Promise<Int16Array>
  /** Hard stop: release mic/context immediately and discard (cancel path). */
  dispose: () => void
}

export type PttCaptureOptions = {
  /** Tee for each converted PCM chunk (the streaming lane). Not called after
   *  drain()/dispose(). */
  onChunk?: (pcm: Int16Array) => void
  /** Fired once if the buffer hits MAX_BUFFER_BYTES; capture keeps running but
   *  stops appending (the first 4.5 min is what gets transcribed). */
  onCapped?: () => void
}

export async function startPttCapture(opts: PttCaptureOptions = {}): Promise<PttCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const ctx = new AudioContext({ sampleRate: 16000 })
  const source = ctx.createMediaStreamSource(stream)

  const analyser = ctx.createAnalyser()
  analyser.fftSize = 64 // 32 bins; the visualizer uses the low end
  analyser.smoothingTimeConstant = 0.85 // smooth, springy bars
  source.connect(analyser)

  const processor = ctx.createScriptProcessor(4096, 1, 1)
  source.connect(processor)

  const chunks: Int16Array[] = []
  let bufferedBytes = 0
  let capped = false
  let stopped = false

  processor.onaudioprocess = (e): void => {
    if (stopped) return
    const f32 = e.inputBuffer.getChannelData(0)
    const i16 = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]))
      i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    if (bufferedBytes + i16.byteLength <= MAX_BUFFER_BYTES) {
      chunks.push(i16)
      bufferedBytes += i16.byteLength
    } else if (!capped) {
      capped = true
      opts.onCapped?.()
    }
    if (!capped) opts.onChunk?.(i16)
  }
  processor.connect(ctx.destination)

  const teardown = (): void => {
    stopped = true
    try {
      processor.disconnect()
    } catch {
      /* ignore */
    }
    try {
      source.disconnect()
    } catch {
      /* ignore */
    }
    try {
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      /* ignore */
    }
    try {
      void ctx.close()
    } catch {
      /* ignore */
    }
  }

  const concatChunks = (): Int16Array => {
    const out = new Int16Array(bufferedBytes / 2)
    let off = 0
    for (const c of chunks) {
      out.set(c, off)
      off += c.length
    }
    return out
  }

  let drainPromise: Promise<Int16Array> | null = null
  return {
    analyser,
    drain: (): Promise<Int16Array> => {
      drainPromise ??= new Promise<Int16Array>((resolve) => {
        setTimeout(() => {
          teardown()
          resolve(concatChunks())
        }, DRAIN_MS)
      })
      return drainPromise
    },
    dispose: teardown
  }
}
