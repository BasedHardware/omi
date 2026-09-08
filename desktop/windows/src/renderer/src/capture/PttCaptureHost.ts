import { useEffect } from 'react'
import {
  warmPttMic,
  releasePttMic,
  startPttCapture,
  rebuildWarmGraph,
  type PttCapture
} from './pttGraph'
import type { CaptureEvent } from '../../../shared/types'

// The capture window's push-to-talk command server. Drives the warm mic graph
// (pttGraph.ts) in response to ptt-* commands from the overlay's PTT hook, and
// streams the results back as routed events:
//   ptt-chunk   — each PCM frame (backfill seed first, then live), to the owner
//   ptt-levels  — ~30fps 32-bin waveform snapshots for the visualizer
//   ptt-capped  — the 4.5-min buffer cap was hit
//   ptt-drained — the full captured buffer, answering a ptt-drain
//   ptt-error   — the mic failed to start
// Module-singleton job map keyed by captureId so the server is idempotent under
// StrictMode / duplicate commands; the component only owns the subscription.

const LEVELS_INTERVAL_MS = 33 // ~30fps

type PttJob = {
  ownerId: number
  capture: PttCapture | null
  capturePromise: Promise<PttCapture> | null
  levelsTimer: ReturnType<typeof setInterval> | null
  disposed: boolean
}

const jobs = new Map<string, PttJob>()

function emit(event: CaptureEvent, ownerId: number): void {
  window.omi?.captureEmit(event, ownerId)
}

/** Copy the chunk into its own ArrayBuffer — backfill chunks are subarray views
 *  into the ring, so we must send only this chunk's bytes (and a standalone
 *  buffer the structured clone can carry). */
function pcmToBuffer(pcm: Int16Array): ArrayBuffer {
  return pcm.slice().buffer
}

function stopLevels(job: PttJob): void {
  if (job.levelsTimer) {
    clearInterval(job.levelsTimer)
    job.levelsTimer = null
  }
}

/** Canonical orb loudness: linear peak amplitude 0..1 over the orb analyser's
 *  time-domain window (fftSize 1024 ≈ 64ms @16kHz) — the SAME unit as the hub
 *  driver's pcmPeakLevel, so the orb's adaptive AmplitudeMapper sees one scale
 *  regardless of which voice path produced the level. (The old byte-frequency
 *  RMS ×2.2 was a dB-domain quantity on a different scale entirely — the curve
 *  calibrated to it silently broke when the hub path shipped linear peaks.) */
function orbLevelFrom(analyser: AnalyserNode, scratch: Float32Array<ArrayBuffer>): number {
  analyser.getFloatTimeDomainData(scratch)
  let peak = 0
  for (let i = 0; i < scratch.length; i++) {
    const v = scratch[i] < 0 ? -scratch[i] : scratch[i]
    if (v > peak) peak = v
  }
  return peak
}

function startLevels(captureId: string, job: PttJob): void {
  const analyser = job.capture!.analyser
  const orbAnalyser = job.capture!.orbAnalyser
  const bins = new Uint8Array(analyser.frequencyBinCount) // 32 bins (fftSize 64)
  const orbScratch = new Float32Array(orbAnalyser.fftSize)
  job.levelsTimer = setInterval(() => {
    analyser.getByteFrequencyData(bins)
    emit(
      {
        type: 'ptt-levels',
        captureId,
        bins: Array.from(bins),
        orbLevel: orbLevelFrom(orbAnalyser, orbScratch)
      },
      job.ownerId
    )
  }, LEVELS_INTERVAL_MS)
}

function startCapture(captureId: string, backfillMs: number, ownerId: number): void {
  if (jobs.has(captureId)) return // idempotent
  const job: PttJob = {
    ownerId,
    capture: null,
    capturePromise: null,
    levelsTimer: null,
    disposed: false
  }
  jobs.set(captureId, job)
  job.capturePromise = startPttCapture({
    // These fire during startPttCapture (backfill seed) and after (live chunks),
    // in order — the client replays them into its buffer + stream lane.
    onChunk: (pcm) => emit({ type: 'ptt-chunk', captureId, pcm: pcmToBuffer(pcm) }, ownerId),
    onCapped: () => emit({ type: 'ptt-capped', captureId }, ownerId),
    backfillMs
  })
    .then((capture) => {
      if (job.disposed) {
        capture.dispose()
        throw new Error('disposed before ready')
      }
      job.capture = capture
      startLevels(captureId, job)
      return capture
    })
    .catch((err: Error) => {
      if (!job.disposed) emit({ type: 'ptt-error', captureId, message: err.message }, ownerId)
      jobs.delete(captureId)
      throw err
    })
  // Prevent an unhandled rejection when no drain awaits a failed start.
  job.capturePromise.catch(() => {})
}

async function drainCapture(captureId: string): Promise<void> {
  const job = jobs.get(captureId)
  if (!job) return
  try {
    const capture = await job.capturePromise
    if (capture) {
      const pcm = await capture.drain()
      stopLevels(job)
      emit({ type: 'ptt-drained', captureId, pcm: pcmToBuffer(pcm) }, job.ownerId)
    }
  } catch {
    /* start failed — ptt-error was already emitted; nothing to drain */
  }
  jobs.delete(captureId)
}

function disposeCapture(captureId: string): void {
  const job = jobs.get(captureId)
  if (!job) return
  job.disposed = true
  stopLevels(job)
  job.capture?.dispose()
  jobs.delete(captureId)
}

export function PttCaptureHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd, ownerId) => {
      switch (cmd.type) {
        case 'ptt-warm':
          void warmPttMic()
          break
        case 'ptt-release':
          releasePttMic()
          break
        case 'ptt-rebuild':
          // Silent-mic recovery (A7b): the hook owns the silent_mic telemetry, so
          // rebuild without emitting the device-change ptt_capture events.
          rebuildWarmGraph('silent_mic', false)
          break
        case 'ptt-start':
          startCapture(cmd.captureId, cmd.backfillMs, ownerId)
          break
        case 'ptt-drain':
          void drainCapture(cmd.captureId)
          break
        case 'ptt-dispose':
          disposeCapture(cmd.captureId)
          break
      }
    })
  }, [])
  return null
}
