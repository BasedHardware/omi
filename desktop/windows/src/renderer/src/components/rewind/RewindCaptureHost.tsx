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
    let captureRunning = false
    let queuedGeneration: number | null = null
    let activeSourceId: string | null = null

    const stop = (): void => {
      generation++
      queuedGeneration = null
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      activeSourceId = null
      if (videoRef.current) videoRef.current.srcObject = null
    }

    const hasUsableVideoTrack = (stream = streamRef.current): boolean =>
      stream?.getVideoTracks().some((t) => t.readyState === 'live' && !t.muted) ?? false

    // #10504/#10737: a desktop-capture track can end or stay "live" while
    // muted (temporarily unable to provide media) after display sleep, a
    // GPU/driver reset, or a session change. Both states otherwise leave the
    // sampler drawing blank frames indefinitely. Re-open the stream through one
    // bounded recovery path.
    // Our own track.stop() does not fire these events, so this cannot self-trigger.
    const onTrackUnavailable = (track?: MediaStreamTrack): void => {
      const currentTracks = streamRef.current?.getVideoTracks() ?? []
      if (cancelled || (track && !currentTracks.includes(track)) || hasUsableVideoTrack()) return
      console.warn('[rewind] capture track unavailable — reopening stream')
      stop()
      timerRef.current = setTimeout(() => void start(), RESTART_DELAY_MS)
    }

    const replaceStream = async (sourceId: string, gen: number): Promise<boolean> => {
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
            // Resolution follows the user's quality tier; every display stays
            // at 1fps so following focus does not add another persistent stream.
            maxWidth: tier.maxWidth,
            maxHeight: tier.maxHeight,
            maxFrameRate: 1
          }
        }
      })
      if (cancelled || gen !== generation) {
        stream.getTracks().forEach((track) => track.stop())
        return false
      }

      const previous = streamRef.current
      previous?.getTracks().forEach((track) => track.stop())
      streamRef.current = stream
      activeSourceId = sourceId
      stream.getVideoTracks().forEach((track) => {
        track.addEventListener('ended', () => onTrackUnavailable(track))
        track.addEventListener('mute', () => onTrackUnavailable(track))
      })
      const video = videoRef.current
      if (video) {
        video.srcObject = stream
        await video.play().catch(() => undefined)
      }
      if (cancelled || gen !== generation || streamRef.current !== stream) {
        stream.getTracks().forEach((track) => track.stop())
        return false
      }
      if (!hasUsableVideoTrack(stream)) {
        onTrackUnavailable(stream.getVideoTracks()[0])
        return false
      }
      return true
    }

    const captureOnce = async (gen: number): Promise<void> => {
      if (cancelled || gen !== generation) return
      try {
        const targetSourceId = await window.omi.rewindCaptureSourceId()
        if (targetSourceId && targetSourceId !== activeSourceId) {
          const replaced = await replaceStream(targetSourceId, gen)
          if (!replaced) return
        }

        const v = videoRef.current
        if (!v || !hasUsableVideoTrack() || !v.videoWidth || !v.videoHeight || savingRef.current)
          return

        savingRef.current = true
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
          if (blob && activeSourceId && !cancelled && gen === generation) {
            await window.omi.rewindSaveFrame(
              new Uint8Array(await blob.arrayBuffer()),
              activeSourceId
            )
          }
        }
      } catch (e) {
        console.error('[rewind] sample failed:', (e as Error).message)
      } finally {
        savingRef.current = false
      }
    }

    // Periodic and foreground-triggered requests share one serial drain. Bursts
    // coalesce to one pending sample, while the next periodic timer is armed only
    // after all requested work settles.
    function scheduleNext(gen: number): void {
      if (cancelled || gen !== generation || !hasUsableVideoTrack()) return
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        requestCapture(gen)
      }, intervalMs)
    }

    function requestCapture(gen: number): void {
      if (cancelled || gen !== generation || !hasUsableVideoTrack()) return
      if (captureRunning) {
        queuedGeneration = gen
        return
      }

      captureRunning = true
      void (async () => {
        let nextGeneration: number | null = gen
        let processedGeneration: number | null = null
        try {
          while (nextGeneration !== null && !cancelled) {
            const requestedGeneration = nextGeneration
            queuedGeneration = null
            await captureOnce(requestedGeneration)
            processedGeneration = requestedGeneration
            nextGeneration = queuedGeneration
          }
        } finally {
          captureRunning = false
          queuedGeneration = null
          if (!cancelled && processedGeneration === generation && hasUsableVideoTrack()) {
            scheduleNext(generation)
          }
        }
      })()
    }

    const start = async (): Promise<void> => {
      try {
        const sourceId = await window.omi.rewindCaptureSourceId()
        if (!sourceId || cancelled) return
        const gen = generation
        if (await replaceStream(sourceId, gen)) scheduleNext(gen)
      } catch (e) {
        console.error('[rewind] failed to start capture:', (e as Error).message)
      }
    }

    const captureNow = (): void => {
      if (!enabled || cancelled || !hasUsableVideoTrack()) return
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      requestCapture(generation)
    }
    const offCaptureNow = window.omi.onRewindCaptureNow(captureNow)

    if (enabled) void start()
    else stop()

    return () => {
      cancelled = true
      offCaptureNow()
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
