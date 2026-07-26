import { useEffect, useRef, useState } from 'react'
import type {
  RewindSettings,
  RewindCaptureDirective,
  RewindCaptureQuality
} from '../../../../shared/types'

// What each quality tier costs and buys. `maxWidth`/`maxHeight` cap the live
// stream (the steady-state cost of having capture on); `maxEdge` caps the
// sampled canvas and `jpegQuality` the encode — both raised with the tier, since
// a sharper stream re-compressed at 0.6 into a 1600px canvas would be spent for
// nothing. 720p at 0.6 is unreadable for small on-screen text, which is why OCR
// misses it (#10489); the sharper tiers are the fix, opt-in because they decode
// and store more all day long.
const QUALITY_TIERS: Record<
  RewindCaptureQuality,
  { maxWidth: number; maxHeight: number; maxEdge: number; jpegQuality: number }
> = {
  standard: { maxWidth: 1280, maxHeight: 720, maxEdge: 1600, jpegQuality: 0.6 },
  high: { maxWidth: 1920, maxHeight: 1080, maxEdge: 1920, jpegQuality: 0.72 },
  max: { maxWidth: 2560, maxHeight: 1440, maxEdge: 2560, jpegQuality: 0.82 }
}
// Wait before re-opening a stream whose track died, so a source that is
// unavailable in bursts (display asleep, GPU reset) can't spin getUserMedia.
const RESTART_DELAY_MS = 2000

/**
 * Background screen-capture host for Rewind. Mounted app-wide (while the window
 * is open). When capture is enabled it opens ONE persistent getUserMedia desktop
 * stream into a hidden <video> — the app's proven, GPU-friendly capture path —
 * then samples frames by drawing the video to a
 * canvas on a self-pacing timer and hands each JPEG to the main process. This
 * deliberately avoids Electron's desktopCapturer full-resolution thumbnail path,
 * which stalled the whole system when polled.
 */
export function RewindCaptureHost(): React.JSX.Element {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const savingRef = useRef(false)
  const [settings, setSettings] = useState<RewindSettings | null>(null)
  // Runtime directive from main (pause + effective cadence), derived from OS
  // power/lock state. Preferred over the persisted interval once received; null
  // until the first fetch/push, when we fall back to the base settings interval.
  const [directive, setDirective] = useState<RewindCaptureDirective | null>(null)

  // Load settings once, then react to changes pushed from the Settings page.
  useEffect(() => {
    void window.omi.rewindGetSettings().then(setSettings)
    return window.omi.onRewindSettings(setSettings)
  }, [])

  // Fetch the current capture directive on mount, then react to pushes. Subscribe
  // BEFORE the fetch and drop the fetched value once any push has landed, so a
  // push that arrives mid-fetch (e.g. a lock's paused:true) can't be clobbered by
  // the now-stale getter result.
  useEffect(() => {
    const pushed = { current: false }
    const unsub = window.omi.onRewindCaptureDirective((d) => {
      pushed.current = true
      setDirective(d)
    })
    void window.omi.rewindGetCaptureDirective().then((d) => {
      if (!pushed.current) setDirective(d)
    })
    return unsub
  }, [])

  // Effective cadence prefers the directive (base × battery); pause tears the
  // stream down (sleep/lock). Fall back to the base interval before first directive.
  const effectiveIntervalMs = directive?.intervalMs ?? settings?.intervalMs ?? 1000
  const paused = directive?.paused ?? false
  const quality = settings?.captureQuality ?? 'standard'

  useEffect(() => {
    const enabled = !!settings?.captureEnabled && !paused
    const intervalMs = effectiveIntervalMs
    const tier = QUALITY_TIERS[quality] ?? QUALITY_TIERS.standard
    let cancelled = false
    // Bumped on every teardown so a grab still in flight (a save is an IPC
    // round-trip) can't reschedule itself onto a stream that is already gone —
    // otherwise each recovery would leave an extra sampling loop running.
    let generation = 0

    const stop = (): void => {
      generation++
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }

    const isLive = (): boolean =>
      streamRef.current?.getVideoTracks().some((t) => t.readyState === 'live') ?? false

    // A desktop-capture track can die while the app keeps running (display sleep,
    // GPU/driver reset, resolution or session change). Nothing used to notice: the
    // sampler kept drawing a dead <video>, so the timeline filled with blank frames
    // and capture never came back. Re-open the stream instead. Our own teardown
    // uses track.stop(), which does not fire 'ended', so this can't self-trigger.
    const onTrackEnded = (): void => {
      if (cancelled) return
      console.warn('[rewind] capture track ended — reopening stream')
      stop()
      timerRef.current = setTimeout(() => void start(), RESTART_DELAY_MS)
    }

    // Self-pacing: schedule the next grab only after the current one settles, so
    // a slow save can never stack concurrent captures.
    const grabAndSchedule = async (gen: number): Promise<void> => {
      if (cancelled || gen !== generation) return
      try {
        const v = videoRef.current
        if (v && isLive() && v.videoWidth && v.videoHeight && !savingRef.current) {
          const scale = Math.min(1, tier.maxEdge / Math.max(v.videoWidth, v.videoHeight))
          const w = Math.round(v.videoWidth * scale)
          const h = Math.round(v.videoHeight * scale)
          const canvas = canvasRef.current ?? (canvasRef.current = document.createElement('canvas'))
          if (canvas.width !== w) canvas.width = w
          if (canvas.height !== h) canvas.height = h
          const ctx = canvas.getContext('2d')
          if (ctx) {
            ctx.drawImage(v, 0, 0, w, h)
            const blob = await new Promise<Blob | null>((r) =>
              canvas.toBlob(r, 'image/jpeg', tier.jpegQuality)
            )
            if (blob && !cancelled && gen === generation) {
              savingRef.current = true
              try {
                await window.omi.rewindSaveFrame(new Uint8Array(await blob.arrayBuffer()))
              } finally {
                savingRef.current = false
              }
            }
          }
        }
      } catch (e) {
        console.error('[rewind] sample failed:', (e as Error).message)
      } finally {
        if (!cancelled && gen === generation) {
          timerRef.current = setTimeout(() => void grabAndSchedule(gen), intervalMs)
        }
      }
    }

    const start = async (): Promise<void> => {
      try {
        const sourceId = await window.omi.rewindPrimarySourceId()
        if (!sourceId || cancelled) return
        const stream = await (
          navigator.mediaDevices as unknown as {
            getUserMedia: (c: unknown) => Promise<MediaStream>
          }
        ).getUserMedia({
          audio: false,
          video: {
            mandatory: {
              chromeMediaSource: 'desktop',
              chromeMediaSourceId: sourceId,
              // The live stream is decoded continuously in the renderer, so its
              // resolution + frame rate set the steady-state cost of having
              // capture on. Resolution follows the user's quality tier (720p by
              // default); the frame rate stays at 1fps regardless — we sample
              // every few seconds, and frame rate is what made this expensive
              // before (1080p@30fps → froze; 1080p@2fps → laggy).
              maxWidth: tier.maxWidth,
              maxHeight: tier.maxHeight,
              maxFrameRate: 1
            }
          }
        })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        stream.getVideoTracks().forEach((t) => t.addEventListener('ended', onTrackEnded))
        const gen = generation
        const v = videoRef.current
        if (v) {
          v.srcObject = stream
          await v.play().catch(() => undefined)
        }
        timerRef.current = setTimeout(() => void grabAndSchedule(gen), intervalMs)
      } catch (e) {
        console.error('[rewind] failed to start capture:', (e as Error).message)
      }
    }

    if (enabled) void start()
    else stop()

    return () => {
      cancelled = true
      stop()
    }
    // `quality` is a stream constraint, so changing it re-opens the stream —
    // otherwise the new tier would only take effect at the next app launch.
  }, [settings?.captureEnabled, effectiveIntervalMs, paused, quality])

  return (
    <video
      ref={videoRef}
      muted
      className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0"
    />
  )
}
