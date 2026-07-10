// Push-to-talk mic capture with a WARM shared graph.
//
// Cold mic startup (getUserMedia + AudioContext init) costs 150-400ms on Windows,
// and the Space gesture already needs a 350ms hold threshold before recording may
// begin (a tap must still type a space) — together that swallowed the first
// ~0.5-0.75s of speech. So the graph is acquired AT SPACE KEY-DOWN (the hook
// calls warmPttMic then; macOS likewise starts capture at key-down) and kept
// briefly warm between presses (MIC_IDLE_RELEASE_MS), then released — the mic
// never idles open while the user is just reading:
//
//   - audio flows into a small ROLLING pre-roll ring (~2s) that is otherwise
//     discarded — nothing is stored or sent while no hold is attached;
//   - a hold ATTACHES to the running graph instantly and BACKFILLS from the ring
//     back to the key-down moment (bounded by when the mic actually went live),
//     so the 350ms threshold costs zero speech;
//   - release/drain only detaches the hold; the graph stays warm for the idle
//     window so consecutive holds don't re-pay spin-up.
//
// Without a warm graph (first press still spinning up, or released), a capture
// falls back to a cold ephemeral graph — same behavior, minus backfill.
//
// A capture feeds three consumers: the bounded local PCM buffer (the foundation
// every transcription lane reads from), the waveform AnalyserNode, and an onChunk
// tee for the opportunistic streaming lane.
import { DRAIN_MS, MAX_BUFFER_BYTES } from './constants'

/** How much already-heard audio the warm graph retains for backfill. Must cover
 *  the 350ms hold threshold plus scheduling jitter; anything older is discarded. */
const PRE_ROLL_MS = 2000
const SAMPLE_RATE = 16000

export type PttCapture = {
  /** Live analyser for the waveform visualizer. */
  analyser: AnalyserNode
  /** Stop appending new audio and, after DRAIN_MS (so the in-flight
   *  ScriptProcessor window lands), resolve the full captured buffer. Idempotent —
   *  repeat calls share one promise. Detaches from a warm graph (which keeps
   *  running) or tears down an ephemeral one. */
  drain: () => Promise<Int16Array>
  /** Hard stop: detach immediately and discard (cancel path). */
  dispose: () => void
}

export type PttCaptureOptions = {
  /** Tee for each converted PCM chunk (the streaming lane). Not called after
   *  drain()/dispose(). */
  onChunk?: (pcm: Int16Array) => void
  /** Fired once if the buffer hits MAX_BUFFER_BYTES; capture keeps running but
   *  stops appending (the first 4.5 min is what gets transcribed). */
  onCapped?: () => void
  /** Include this much already-heard audio from the warm pre-roll ring — the
   *  hook passes the time since key-down so the hold threshold costs no speech.
   *  Ignored on a cold start (there is no past audio to include). */
  backfillMs?: number
}

/** One live mic graph: stream → source → { analyser, processor }. The processor
 *  converts to Int16 once and fans out to the pre-roll ring + attached captures. */
type MicGraph = {
  stream: MediaStream
  ctx: AudioContext
  source: MediaStreamAudioSourceNode
  processor: ScriptProcessorNode
  analyser: AnalyserNode
  subscribers: Set<(pcm: Int16Array) => void>
  ring: Int16Array[]
  ringSamples: number
}

async function createGraph(): Promise<MicGraph> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source = ctx.createMediaStreamSource(stream)

  const analyser = ctx.createAnalyser()
  analyser.fftSize = 64 // 32 bins; the visualizer uses the low end
  analyser.smoothingTimeConstant = 0.85 // smooth, springy bars
  source.connect(analyser)

  const processor = ctx.createScriptProcessor(4096, 1, 1)
  source.connect(processor)

  const graph: MicGraph = {
    stream,
    ctx,
    source,
    processor,
    analyser,
    subscribers: new Set(),
    ring: [],
    ringSamples: 0
  }

  const ringCap = (PRE_ROLL_MS / 1000) * SAMPLE_RATE
  processor.onaudioprocess = (e): void => {
    const f32 = e.inputBuffer.getChannelData(0)
    const i16 = new Int16Array(f32.length)
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]))
      i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    graph.ring.push(i16)
    graph.ringSamples += i16.length
    while (graph.ringSamples - graph.ring[0].length >= ringCap) {
      graph.ringSamples -= graph.ring.shift()!.length
    }
    for (const sub of graph.subscribers) sub(i16)
  }
  processor.connect(ctx.destination)
  return graph
}

function destroyGraph(graph: MicGraph): void {
  try {
    graph.processor.disconnect()
  } catch {
    /* ignore */
  }
  try {
    graph.source.disconnect()
  } catch {
    /* ignore */
  }
  try {
    graph.stream.getTracks().forEach((t) => t.stop())
  } catch {
    /* ignore */
  }
  try {
    void graph.ctx.close()
  } catch {
    /* ignore */
  }
}

/** The most recent `ms` of audio from the ring, trimmed to the sample so nothing
 *  from BEFORE the requested window (i.e. before key-down) leaks in. */
function backfillFromRing(graph: MicGraph, ms: number): Int16Array[] {
  const want = Math.min(Math.round((ms / 1000) * SAMPLE_RATE), graph.ringSamples)
  if (want <= 0) return []
  const out: Int16Array[] = []
  let have = 0
  for (let i = graph.ring.length - 1; i >= 0 && have < want; i--) {
    const chunk = graph.ring[i]
    const need = want - have
    out.unshift(need >= chunk.length ? chunk : chunk.subarray(chunk.length - need))
    have += Math.min(chunk.length, need)
  }
  return out
}

// --- Warm-graph lifecycle (driven by the overlay's focus) ---------------------

let warmGraph: MicGraph | null = null
let warmPromise: Promise<MicGraph> | null = null
let attachedCaptures = 0
let releaseWanted = false

/** Open (or keep) the warm mic graph. Idempotent; resolves false if the mic is
 *  unavailable (permission denied / no device) — holds then cold-start and fail
 *  visibly through the normal capture path. */
export async function warmPttMic(): Promise<boolean> {
  releaseWanted = false
  if (warmGraph) return true
  warmPromise ??= createGraph()
  try {
    const graph = await warmPromise
    // A release may have arrived while the graph was being created.
    if (releaseWanted) {
      destroyGraph(graph)
      return false
    }
    warmGraph = graph
    return true
  } catch {
    return false
  } finally {
    warmPromise = null
  }
}

/** Release the warm graph (overlay hidden/blurred). If a hold is mid-capture the
 *  teardown is deferred until it detaches, so an in-flight capture never loses
 *  its mic. */
export function releasePttMic(): void {
  releaseWanted = true
  if (warmGraph && attachedCaptures === 0) {
    destroyGraph(warmGraph)
    warmGraph = null
  }
}

function maybeReleaseWarm(): void {
  if (releaseWanted && warmGraph && attachedCaptures === 0) {
    destroyGraph(warmGraph)
    warmGraph = null
  }
}

// --- Captures ------------------------------------------------------------------

export async function startPttCapture(opts: PttCaptureOptions = {}): Promise<PttCapture> {
  // The key-down acquisition may still be spinning up when the hold threshold
  // fires — wait for it rather than opening a second mic stream.
  let warm = warmGraph
  if (!warm && warmPromise) {
    try {
      await warmPromise
    } catch {
      /* fall through to the cold path (which will surface mic failures) */
    }
    warm = warmGraph
  }
  const graph = warm ?? (await createGraph())
  const ephemeral = !warm
  if (!ephemeral) attachedCaptures++

  // Seed with pre-roll audio back to key-down (warm graph only — a cold graph
  // has no past to include).
  const chunks: Int16Array[] = ephemeral ? [] : backfillFromRing(graph, opts.backfillMs ?? 0)
  let bufferedBytes = chunks.reduce((n, c) => n + c.byteLength, 0)
  let capped = false
  let detached = false

  // The stream lane must hear the backfill too — otherwise a fast stream commit
  // would be missing the opening words that only the batch buffer had.
  for (const c of chunks) opts.onChunk?.(c)

  const onPcm = (i16: Int16Array): void => {
    if (bufferedBytes + i16.byteLength <= MAX_BUFFER_BYTES) {
      chunks.push(i16)
      bufferedBytes += i16.byteLength
      opts.onChunk?.(i16)
    } else if (!capped) {
      capped = true
      opts.onCapped?.()
    }
  }
  graph.subscribers.add(onPcm)

  const detach = (): void => {
    if (detached) return
    detached = true
    graph.subscribers.delete(onPcm)
    if (ephemeral) {
      destroyGraph(graph)
    } else {
      attachedCaptures--
      maybeReleaseWarm()
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
    analyser: graph.analyser,
    drain: (): Promise<Int16Array> => {
      drainPromise ??= new Promise<Int16Array>((resolve) => {
        setTimeout(() => {
          detach()
          resolve(concatChunks())
        }, DRAIN_MS)
      })
      return drainPromise
    },
    dispose: detach
  }
}
