// Push-to-talk mic graph — moved verbatim (behavior-preserving) from
// lib/ptt/capture.ts into the capture window, which now owns all mic capture. The
// UI-side lib/ptt/capture.ts is a thin IPC client that drives this over the
// capture bridge; PttCaptureHost.ts is the command server that calls into here.
//
// Cold mic startup (getUserMedia + AudioContext init) costs 150-400ms on Windows,
// and the Space gesture already needs a 350ms hold threshold before recording may
// begin (a tap must still type a space) — together that swallowed the first
// ~0.5-0.75s of speech. So the graph is acquired AT SPACE KEY-DOWN (the hook
// sends ptt-warm then) and kept briefly warm between presses, then released — the
// mic never idles open while the user is just reading:
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
import { acquireMicStream, floatTo16BitPCM, teardownAudioGraph } from '../lib/audio'
import { DRAIN_MS, MAX_BUFFER_BYTES } from '../lib/ptt/constants'

/** How much already-heard audio the warm graph retains for backfill. Must cover
 *  the 350ms hold threshold plus scheduling jitter; anything older is discarded. */
const PRE_ROLL_MS = 2000
const SAMPLE_RATE = 16000

export type PttCapture = {
  /** Live analyser for the waveform visualizer (heavily smoothed → springy bars). */
  analyser: AnalyserNode
  /** Second analyser with (near-)zero smoothing, for the orb's per-syllable
   *  reactivity. The bars' smoothing lags ~600ms — too slow for the blob — so
   *  the orb reads its own fast tap and does its own (fast attack / slow
   *  release) shaping downstream. */
  orbAnalyser: AnalyserNode
  /** Stop appending new audio and, after DRAIN_MS (so the in-flight
   *  ScriptProcessor window lands), resolve the full captured buffer. Idempotent —
   *  repeat calls share one promise. Detaches from a warm graph (which keeps
   *  running) or tears down an ephemeral one. */
  drain: () => Promise<Int16Array>
  /** Hard stop: detach immediately and discard (cancel path). */
  dispose: () => void
}

export type PttCaptureOptions = {
  /** Tee for each PCM chunk, INCLUDING the backfill seed (the streaming lane must
   *  hear the same audio the batch buffer holds). Not called after
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
  orbAnalyser: AnalyserNode
  subscribers: Set<(pcm: Int16Array) => void>
  ring: Int16Array[]
  ringSamples: number
}

/** `trackRing: false` for ephemeral (cold) graphs — nothing ever reads their
 *  pre-roll, so skip the per-chunk ring bookkeeping. */
async function createGraph(trackRing: boolean): Promise<MicGraph> {
  const stream = await acquireMicStream()
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source = ctx.createMediaStreamSource(stream)

  const analyser = ctx.createAnalyser()
  analyser.fftSize = 64 // 32 bins; the visualizer uses the low end
  analyser.smoothingTimeConstant = 0.85 // smooth, springy bars
  source.connect(analyser)

  // A second, (near-)zero-smoothing analyser dedicated to the orb: the bars'
  // 0.85 smoothing lags ~600ms and mutes syllable transients. This one passes
  // the raw per-poll level through; the orb's own envelope does the shaping.
  const orbAnalyser = ctx.createAnalyser()
  orbAnalyser.fftSize = 64
  orbAnalyser.smoothingTimeConstant = 0.2
  source.connect(orbAnalyser)

  const processor = ctx.createScriptProcessor(4096, 1, 1)
  source.connect(processor)

  const graph: MicGraph = {
    stream,
    ctx,
    source,
    processor,
    analyser,
    orbAnalyser,
    subscribers: new Set(),
    ring: [],
    ringSamples: 0
  }

  const ringCap = (PRE_ROLL_MS / 1000) * SAMPLE_RATE
  processor.onaudioprocess = (e): void => {
    const i16 = floatTo16BitPCM(e.inputBuffer.getChannelData(0))
    if (trackRing) {
      graph.ring.push(i16)
      graph.ringSamples += i16.length
      while (graph.ringSamples - graph.ring[0].length >= ringCap) {
        graph.ringSamples -= graph.ring.shift()!.length
      }
    }
    for (const sub of graph.subscribers) sub(i16)
  }
  processor.connect(ctx.destination)
  return graph
}

function destroyGraph(graph: MicGraph): void {
  teardownAudioGraph({
    nodes: [graph.processor, graph.source],
    stream: graph.stream,
    ctx: graph.ctx
  })
}

/** The most recent `ms` of audio from the ring, trimmed to the sample so nothing
 *  from BEFORE the requested window (i.e. before key-down) leaks in. Exported (and
 *  taking just the ring fields) so the order/trim logic is unit-testable without a
 *  live AudioContext. */
export function backfillFromRing(
  ring: Int16Array[],
  ringSamples: number,
  ms: number
): Int16Array[] {
  const want = Math.min(Math.round((ms / 1000) * SAMPLE_RATE), ringSamples)
  if (want <= 0) return []
  const out: Int16Array[] = []
  let have = 0
  for (let i = ring.length - 1; i >= 0 && have < want; i--) {
    const chunk = ring[i]
    const need = want - have
    out.unshift(need >= chunk.length ? chunk : chunk.subarray(chunk.length - need))
    have += Math.min(chunk.length, need)
  }
  return out
}

// --- Warm-graph lifecycle (driven by the host: key-down warm, idle release) ----

let warmGraph: MicGraph | null = null
let warmPromise: Promise<MicGraph> | null = null
let attachedCaptures = 0
let releaseWanted = false

/** Open (or keep) the warm mic graph. Idempotent; failures are swallowed here —
 *  a hold then cold-starts and surfaces mic errors through the capture path. */
export async function warmPttMic(): Promise<void> {
  releaseWanted = false
  if (warmGraph) return
  warmPromise ??= createGraph(true)
  try {
    const graph = await warmPromise
    // A release may have arrived while the graph was being created.
    if (releaseWanted) destroyGraph(graph)
    else warmGraph = graph
  } catch {
    /* hold-time capture will retry cold and surface the error */
  } finally {
    warmPromise = null
  }
}

/** Release the warm graph (idle linger elapsed, or overlay hidden/blurred). If a
 *  hold is mid-capture the teardown is deferred until it detaches, so an
 *  in-flight capture never loses its mic. */
export function releasePttMic(): void {
  releaseWanted = true
  maybeReleaseWarm()
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
  const graph = warm ?? (await createGraph(false))
  const ephemeral = !warm
  if (!ephemeral) attachedCaptures++

  // Seed with pre-roll audio back to key-down (warm graph only — a cold graph
  // has no past to include).
  const chunks: Int16Array[] = ephemeral
    ? []
    : backfillFromRing(graph.ring, graph.ringSamples, opts.backfillMs ?? 0)
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
    orbAnalyser: graph.orbAnalyser,
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
