// Silero v5 voice-activity model, driven DIRECTLY on onnxruntime-web from the
// capture pipeline's own frames — no @ricky0123/vad-web MicVAD, so there is no
// second getUserMedia and no second audio graph. That keeps ONE mic stream the
// pipeline can release for privacy, while the InferenceSession below lives for the
// whole process.
//
// LIFECYCLE: the InferenceSession is created ONCE per process (loadSession) and is
// NEVER released — onnxruntime-web leaks native memory when a session is recreated,
// so a per-session create/destroy would grow RSS unbounded. Per-capture-session
// state (the model's recurrent [2,1,128] tensor) is external and cheap; each
// detector owns its own, created fresh (zeroed) per session. Per-run input/output/
// old-state tensors ARE disposed so wasm-heap use stays flat across a long soak.
//
// VENDORED: the run/state shape (inputs input|state|sr → outputs output|stateN,
// 512-sample v5 frames, [2,1,128] state) is copied from @ricky0123/vad-web's
// models/v5.js. MAINTENANCE CAVEAT: if the bundled silero_vad_v5.onnx (staged from
// that package by scripts/copy-vad-assets.mjs) is ever replaced with a model whose
// I/O names or state shape differ, this wrapper must be updated to match — the copy
// script pins the source, so a version bump is the trigger to re-check here.
import * as ort from 'onnxruntime-web/wasm'
// Vite-transformed URLs for the ort loader pair. In DEV, vite REFUSES to serve
// /public files as ES module imports ("should not be imported from source
// code"), and ort dynamically import()s its .mjs loader from wasmPaths — so the
// self-hosted /vad/ path only works in production builds. These ?url imports
// give dev-servable module URLs; production keeps /vad/ (the build-emitted
// duplicate wasm is stripped by the drop-duplicate-ort-wasm vite plugin).
import ortMjsUrl from 'onnxruntime-web/ort-wasm-simd-threaded.mjs?url'
import ortWasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.wasm?url'

/** v5 runs on 512-sample (32ms @16kHz) frames. */
export const SILERO_FRAME_SAMPLES = 512

const MODEL_URL = '/vad/silero_vad_v5.onnx'
const STATE_DIMS = [2, 1, 128] as const
const STATE_LEN = 2 * 1 * 128

let sessionPromise: Promise<ort.InferenceSession> | null = null
// onnxruntime-web's wasm runtime is single-threaded and NOT reentrant: two
// overlapping session.run() calls (e.g. the mic + loopback detectors) corrupt each
// other. Serialize every run across all detectors on one chain.
let runLock: Promise<unknown> = Promise.resolve()

function loadSession(): Promise<ort.InferenceSession> {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      ort.env.wasm.wasmPaths = import.meta.env.DEV
        ? { mjs: ortMjsUrl, wasm: ortWasmUrl }
        : '/vad/'
      ort.env.wasm.numThreads = 1 // single-threaded → no COOP/COEP cross-origin isolation needed
      ort.env.logLevel = 'error'
      const res = await fetch(MODEL_URL)
      if (!res.ok) throw new Error(`model fetch failed: ${res.status} ${MODEL_URL}`)
      const bytes = await res.arrayBuffer()
      return ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] })
    })().catch((e) => {
      sessionPromise = null // allow a later session to retry a transient failure
      throw e
    })
  }
  return sessionPromise
}

function dispose(t: ort.Tensor | undefined): void {
  try {
    t?.dispose()
  } catch {
    /* CPU tensors may no-op; ignore */
  }
}

function zeroState(): ort.Tensor {
  return new ort.Tensor('float32', new Float32Array(STATE_LEN), STATE_DIMS.slice())
}

export type SileroDetector = {
  /** Run one 512-sample frame → P(speech) in [0,1]. Rejects if the model errors. */
  process: (frame: Float32Array) => Promise<number>
}

/** Create a detector bound to the shared (once-per-process) session. Awaits the
 *  session load; a load failure rejects so the caller can fall open to passthrough. */
export async function createSileroDetector(): Promise<SileroDetector> {
  const session = await loadSession()
  let state = zeroState()
  const sr = new ort.Tensor('int64', [16000n])

  return {
    process: (frame: Float32Array): Promise<number> => {
      // The whole read-run-write is one critical section on the global lock, so a
      // detector's state can't be read by another run mid-update.
      const result = runLock.then(async () => {
        const input = new ort.Tensor('float32', frame, [1, frame.length])
        const out = await session.run({ input, state, sr })
        const prob = out.output.data[0] as number
        const prevState = state
        state = out.stateN
        dispose(input)
        dispose(out.output)
        dispose(prevState) // free the consumed state so wasm heap stays flat
        return prob
      })
      runLock = result.catch(() => {}) // keep the chain alive after a rejection
      return result
    }
  }
}
