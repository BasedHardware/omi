// Push-to-talk capture — IPC CLIENT. The actual mic graph (warm graph, pre-roll
// ring, backfill) now lives in the capture window (src/renderer/src/capture/
// pttGraph.ts, served by PttCaptureHost). This module preserves the exact surface
// the hook depended on — warmPttMic / releasePttMic / startPttCapture(opts) →
// { analyser, drain, dispose } — but each call is a command to the capture window,
// and audio/levels stream back as routed events. The `analyser` is a
// WaveformSource adapter fed by the latest ptt-levels frame (zeros before the
// first), so the Waveform component is unchanged aside from a structural type.
import { DRAIN_MS } from './constants'
import type { WaveformSource } from '../../../../shared/types'

export type PttCapture = {
  /** Waveform amplitude source, fed by ptt-levels frames from the capture window. */
  analyser: WaveformSource
  /** Ask the capture window to finalize: it stops appending and, after DRAIN_MS,
   *  replies with the full buffer. Idempotent — repeat calls share one promise. */
  drain: () => Promise<Int16Array>
  /** Hard stop: tell the capture window to discard this capture (cancel path). */
  dispose: () => void
}

export type PttCaptureOptions = {
  /** Tee for each PCM chunk (backfill seed first, then live), in order. */
  onChunk?: (pcm: Int16Array) => void
  /** Fired once if the capture window's buffer hits its cap. */
  onCapped?: () => void
  /** Include this much pre-roll from the warm graph's ring — the hook passes the
   *  time since key-down so the hold threshold costs no speech. */
  backfillMs?: number
}

let nextId = 1

/** Warm the capture window's mic graph (called at Space key-down). */
export async function warmPttMic(): Promise<void> {
  window.omi?.captureCommand({ type: 'ptt-warm' })
}

/** Release the warm graph (idle linger, overlay hide/blur). */
export function releasePttMic(): void {
  window.omi?.captureCommand({ type: 'ptt-release' })
}

/**
 * Start a push-to-talk capture in the capture window. Resolves once the capture
 * is confirmed live (first streamed event), or rejects if the mic failed to
 * start — matching the old in-window behavior the hook relies on.
 */
export async function startPttCapture(opts: PttCaptureOptions = {}): Promise<PttCapture> {
  const captureId = `ptt-${Date.now()}-${nextId++}`
  let latestBins: number[] = []
  let latestOrbLevel = 0

  // A live AnalyserNode's getByteFrequencyData, reimplemented off the latest
  // streamed frame; zeros until the first frame arrives. getOrbLevel exposes the
  // fast orb loudness the capture window ships alongside the bar bins.
  const analyser: WaveformSource = {
    getByteFrequencyData: (dest: Uint8Array): void => {
      const n = Math.min(dest.length, latestBins.length)
      for (let i = 0; i < n; i++) dest[i] = latestBins[i]
      for (let i = n; i < dest.length; i++) dest[i] = 0
    },
    getOrbLevel: (): number => latestOrbLevel
  }

  return await new Promise<PttCapture>((resolve, reject) => {
    let started = false
    let disposed = false
    let drainPromise: Promise<Int16Array> | null = null
    let onDrained: ((pcm: Int16Array) => void) | null = null

    const unsub = window.omi.onCaptureEvent((ev) => {
      switch (ev.type) {
        case 'ptt-chunk':
          if (ev.captureId !== captureId) return
          markStarted()
          opts.onChunk?.(new Int16Array(ev.pcm))
          break
        case 'ptt-levels':
          if (ev.captureId !== captureId) return
          markStarted()
          latestBins = ev.bins
          if (ev.orbLevel !== undefined) latestOrbLevel = ev.orbLevel
          break
        case 'ptt-capped':
          if (ev.captureId !== captureId) return
          opts.onCapped?.()
          break
        case 'ptt-error':
          if (ev.captureId !== captureId) return
          unsub()
          if (!started) reject(new Error(ev.message || 'ptt capture failed'))
          break
        case 'ptt-drained':
          if (ev.captureId !== captureId) return
          onDrained?.(new Int16Array(ev.pcm))
          break
        case 'capture-window-restarted':
          // The capture window died mid-hold — abandon this capture. If a drain is
          // waiting, resolve it empty (the hook then discards a silent turn).
          unsub()
          if (!started) reject(new Error('capture window restarted'))
          else onDrained?.(new Int16Array(0))
          break
      }
    })

    function markStarted(): void {
      if (started) return
      started = true
      resolve(capture)
    }

    const capture: PttCapture = {
      analyser,
      drain: (): Promise<Int16Array> => {
        drainPromise ??= new Promise<Int16Array>((res) => {
          // Resolve empty if the capture window doesn't reply in time (dead/mid-
          // restart) — the hook's gate then treats it as a silent/failed turn,
          // rather than hanging until the 25s watchdog.
          const to = setTimeout(() => {
            unsub()
            res(new Int16Array(0))
          }, 2 * DRAIN_MS)
          onDrained = (pcm): void => {
            clearTimeout(to)
            unsub()
            res(pcm)
          }
          window.omi.captureCommand({ type: 'ptt-drain', captureId })
        })
        return drainPromise
      },
      dispose: (): void => {
        if (disposed) return
        disposed = true
        unsub()
        window.omi.captureCommand({ type: 'ptt-dispose', captureId })
      }
    }

    window.omi.captureCommand({ type: 'ptt-start', captureId, backfillMs: opts.backfillMs ?? 0 })
  })
}
