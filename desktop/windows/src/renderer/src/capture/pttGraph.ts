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
import { trackEvent } from '../lib/analytics'

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
  /** AGC-free second stream feeding the orb analyser, hot-swapped in by
   *  attachOrbTap AFTER the graph is live (null until then / on failure — the
   *  orb analyser reads the processed `stream` meanwhile). */
  orbStream: MediaStream | null
  /** Set by destroyGraph so a late-resolving orb tap knows to discard itself. */
  destroyed: boolean
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

  // A second analyser dedicated to the orb: the bars' 0.85 smoothing lags
  // ~600ms and mutes syllable transients. The host reads this one's TIME-DOMAIN
  // window (getFloatTimeDomainData) for a true linear peak — the canonical
  // orbLevel unit, matching the hub driver's pcmPeakLevel — so fftSize sets the
  // peak window: 1024 samples @16kHz ≈ 64ms, fully covering the ~33ms level
  // poll. (smoothingTimeConstant only affects frequency data — irrelevant here.)
  const orbAnalyser = ctx.createAnalyser()
  orbAnalyser.fftSize = 1024

  // Until (and unless) the AGC-free tap below lands, the orb analyser reads the
  // processed stream — compressed but working levels, never a gap.
  source.connect(orbAnalyser)

  const processor = ctx.createScriptProcessor(4096, 1, 1)
  source.connect(processor)

  const graph: MicGraph = {
    stream,
    orbStream: null,
    destroyed: false,
    ctx,
    source,
    processor,
    analyser,
    orbAnalyser,
    subscribers: new Set(),
    ring: [],
    ringSamples: 0
  }

  // Fire-and-forget: the AGC-free orb tap is a visual upgrade and must NEVER
  // gate capture readiness — the graph returns immediately on the fallback
  // wiring and the tap hot-swaps in when (if) it resolves.
  void attachOrbTap(graph)

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

/** Ceiling on the orb tap's device open. The fallback catch fires on REJECT —
 *  a driver wedged on a concurrent same-device open would otherwise hang the
 *  tap forever (harmless to capture, which never waits on it, but the orb
 *  would silently stay on compressed levels with no diagnostic). */
const ORB_TAP_TIMEOUT_MS = 3000

/**
 * Hot-swap the orb analyser onto its OWN AGC-free stream on the SAME device.
 * The main stream keeps getUserMedia's default processing (echoCancellation +
 * noiseSuppression + autoGainControl) — right for STT, but AGC compresses away
 * exactly the loudness dynamics the orb visualizes (measured through VB-Cable:
 * -26dB and -10dB inputs both surfaced ≈ -9dBFS after AGC). EC/NS stay on so
 * playback echo and room hiss don't draw bars; only the gain flattening is
 * removed. STT audio is untouched.
 *
 * Runs DETACHED from graph creation (see the `void attachOrbTap` call site):
 * capture readiness never waits on this acquire, any failure/timeout leaves
 * the fallback wiring (processed-stream levels) in place, and a resolution
 * that arrives after the graph was destroyed discards itself.
 */
async function attachOrbTap(graph: MicGraph): Promise<void> {
  let acquire: Promise<MediaStream> | null = null
  let tap: MediaStream | null = null
  try {
    // Open by the CONCRETE device id, never the 'default'/'communications'
    // alias: Chrome shares one input source per device-id STRING, and a second
    // open of the SAME id silently inherits the first open's processing — the
    // requested autoGainControl:false is ignored and getSettings() reports
    // agc:true (measured). The concrete id forces a separate source with its
    // own processing chain.
    const settings = graph.stream.getAudioTracks()[0]?.getSettings()
    let deviceId = settings?.deviceId
    if (deviceId === 'default' || deviceId === 'communications') {
      const concrete = (await navigator.mediaDevices.enumerateDevices()).find(
        (d) =>
          d.kind === 'audioinput' &&
          d.groupId === settings?.groupId &&
          d.deviceId !== 'default' &&
          d.deviceId !== 'communications'
      )
      if (concrete) deviceId = concrete.deviceId
    }
    acquire = navigator.mediaDevices.getUserMedia({
      audio: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false
      }
    })
    tap = await Promise.race([
      acquire,
      new Promise<never>((_, reject) =>
        setTimeout(
          () => reject(new Error(`orb tap timed out after ${ORB_TAP_TIMEOUT_MS}ms`)),
          ORB_TAP_TIMEOUT_MS
        )
      )
    ])
    if (graph.destroyed) {
      for (const t of tap.getTracks()) t.stop()
      return
    }
    // Honesty check: if the source still got shared, the constraint silently
    // didn't take — that's a failed tap, not a working one.
    if (tap.getAudioTracks()[0]?.getSettings().autoGainControl === true) {
      throw new Error('autoGainControl still on (source was shared)')
    }
    // Swap: connect the tap first, then drop the fallback edge — no gap frame.
    graph.ctx.createMediaStreamSource(tap).connect(graph.orbAnalyser)
    graph.source.disconnect(graph.orbAnalyser)
    graph.orbStream = tap
    console.log(
      '[audio] orb tap active:',
      JSON.stringify(tap.getAudioTracks()[0]?.getSettings() ?? {})
    )
  } catch (e) {
    // Loud on purpose: with the fallback the orb sees AGC-flattened levels, so
    // "the visualizer barely tracks loudness" bugs start here.
    console.warn('[audio] orb AGC-free tap failed — orb levels will be AGC-compressed:', e)
    try {
      tap?.getTracks().forEach((t) => t.stop())
    } catch {
      /* best effort */
    }
    // A timed-out open that resolves LATER must still be stopped — never leak
    // a live mic stream.
    acquire
      ?.then((s) => {
        if (s !== tap) for (const t of s.getTracks()) t.stop()
      })
      .catch(() => {})
  }
}

function destroyGraph(graph: MicGraph): void {
  graph.destroyed = true
  // The orb's AGC-free stream is not part of the shared teardown shape — stop
  // its tracks explicitly or the mic stays open (in-use indicator) after release.
  try {
    graph.orbStream?.getTracks().forEach((t) => t.stop())
  } catch {
    /* already stopped */
  }
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
  // A rebuild ladder (device-change A7a / silent-mic A7b) already owns graph
  // creation and installs the fresh warm graph when it settles. Starting a second
  // createGraph here races it — whichever resolves last wins `warmGraph` and ORPHANS
  // the other (a live mic stream + AudioContext + ScriptProcessorNode still wired to
  // destination that is never torn down). Under PTT stress a key-down warm colliding
  // with a rebuild leaks capture graphs until the audio service crashes. Defer to the
  // in-flight rebuild — releaseWanted is cleared above, so it keeps the graph it makes.
  if (reconfiguring) return
  warmPromise ??= createGraph(true)
  try {
    const graph = await warmPromise
    // A release may have arrived while the graph was being created.
    if (releaseWanted) destroyGraph(graph)
    else {
      warmGraph = graph
      installDeviceChangeListener()
    }
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
  if (releaseWanted && attachedCaptures === 0) teardownWarm()
}

/** Fully drop the warm graph: cancel any in-flight rebuild, destroy the graph,
 *  and stop listening for device changes. */
function teardownWarm(): void {
  stopRebuild(true)
  if (warmGraph) {
    destroyGraph(warmGraph)
    warmGraph = null
  }
  removeDeviceChangeListener()
}

// --- Device-change / silent-mic capture-graph rebuild ---------------------------
// Port of macOS AudioCaptureService.handleConfigurationChange → reconfigureAfterChange
// → retryOrGiveUp: on a default-input swap / format change (A7a) or a silent-mic
// recovery request (A7b), tear down + rebuild the warm getUserMedia/Web-Audio graph
// after a 0.3s settle, retrying with linear 1s/2s/3s backoff (4 attempts total,
// ~6.3s worst case) before giving up. Idempotent — one ladder at a time; cancelled
// on teardown; deferred while a hold is attached so an active capture never loses
// its mic mid-turn.
const REBUILD_SETTLE_MS = 300 // let the OS settle the device swap before reopening
const REBUILD_MAX_RETRIES = 3 // 4 attempts total: initial + 3 linear-backoff retries
const REBUILD_BACKOFF_MS = 1000 // retry N waits N*1000ms (1s, 2s, 3s)

let reconfiguring = false // a rebuild ladder is in flight (guards overlap)
let rebuildTimer: ReturnType<typeof setTimeout> | null = null
let pendingRebuild: { reason: string; emitTelemetry: boolean } | null = null
let deviceChangeInstalled = false

function onDeviceChange(): void {
  // A default-input swap or a format change on the current device — rebuild the
  // warm graph so the next hold captures from the new device. The 0.3s settle +
  // the reconfiguring guard debounce a burst of change events into one rebuild.
  rebuildWarmGraph('device_changed', true)
}

function installDeviceChangeListener(): void {
  if (deviceChangeInstalled) return
  // addEventListener (NOT navigator.mediaDevices.ondevicechange = …) so this
  // coexists with voiceController's headset-detection listener rather than
  // clobbering it.
  navigator.mediaDevices?.addEventListener?.('devicechange', onDeviceChange)
  deviceChangeInstalled = true
}

function removeDeviceChangeListener(): void {
  if (!deviceChangeInstalled) return
  navigator.mediaDevices?.removeEventListener?.('devicechange', onDeviceChange)
  deviceChangeInstalled = false
}

/** Rebuild the warm mic graph. `emitTelemetry` fires the ptt_capture fallback
 *  events (device-change path); the silent-mic path passes false because the hook
 *  owns the silent_mic telemetry. Guarded (no overlap), deferred while a hold is
 *  attached, and a no-op when nothing warm exists (the next hold cold-starts). */
export function rebuildWarmGraph(reason: string, emitTelemetry: boolean): void {
  if (reconfiguring) return // a ladder is already running — no overlap
  if (!warmGraph) return // nothing warm to rebuild; the next hold opens fresh
  if (attachedCaptures > 0) {
    // A hold is mid-capture — don't yank its graph; run once it detaches.
    pendingRebuild = { reason, emitTelemetry }
    return
  }
  reconfiguring = true
  rebuildTimer = setTimeout(() => {
    rebuildTimer = null
    void attemptRebuild(0, reason, emitTelemetry)
  }, REBUILD_SETTLE_MS)
}

async function attemptRebuild(
  retry: number,
  reason: string,
  emitTelemetry: boolean
): Promise<void> {
  if (releaseWanted) {
    stopRebuild(true)
    return
  }
  if (attachedCaptures > 0) {
    // A hold attached AFTER this ladder was scheduled (during the settle/backoff
    // window) — rebuildWarmGraph's up-front guard couldn't have seen it. Don't yank
    // the live graph out from under the active capture: defer and let the detach
    // re-run us via runPendingRebuild. Clearing `reconfiguring` (not keeping it set)
    // is required so the deferred rebuild isn't blocked as an overlap later.
    pendingRebuild = { reason, emitTelemetry }
    stopRebuild(false)
    return
  }
  if (warmGraph) {
    destroyGraph(warmGraph)
    warmGraph = null
  }
  try {
    const graph = await createGraph(true)
    if (releaseWanted) {
      destroyGraph(graph)
      stopRebuild(true)
      return
    }
    warmGraph = graph
    stopRebuild(false)
    if (emitTelemetry) {
      trackEvent('fallback_triggered', {
        component: 'ptt_capture',
        from: 'default_device',
        to: 'rebuilt',
        reason,
        outcome: 'recovered'
      })
    }
  } catch {
    if (retry < REBUILD_MAX_RETRIES && !releaseWanted) {
      rebuildTimer = setTimeout(
        () => {
          rebuildTimer = null
          void attemptRebuild(retry + 1, reason, emitTelemetry)
        },
        (retry + 1) * REBUILD_BACKOFF_MS
      )
    } else {
      stopRebuild(false)
      if (emitTelemetry) {
        trackEvent('fallback_triggered', {
          component: 'ptt_capture',
          from: 'default_device',
          to: 'none',
          reason,
          outcome: 'exhausted'
        })
      }
    }
  }
}

/** End the current ladder. `clearPending` also drops a deferred rebuild (teardown);
 *  a normal terminal keeps none pending anyway. */
function stopRebuild(clearPending: boolean): void {
  reconfiguring = false
  if (rebuildTimer) {
    clearTimeout(rebuildTimer)
    rebuildTimer = null
  }
  if (clearPending) pendingRebuild = null
}

/** Run a rebuild that was deferred while a hold held the warm graph, now that the
 *  last capture has detached. */
function runPendingRebuild(): void {
  if (!pendingRebuild || attachedCaptures !== 0 || releaseWanted || !warmGraph) return
  const { reason, emitTelemetry } = pendingRebuild
  pendingRebuild = null
  rebuildWarmGraph(reason, emitTelemetry)
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
      runPendingRebuild()
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
