import { useEffect, useRef, useState } from 'react'
import type { RewindSettings } from '../../../../shared/types'

// Cap the longest sampled edge — plenty for a timeline + OCR, and keeps each
// canvas grab + JPEG encode cheap.
const MAX_EDGE = 1600
const JPEG_QUALITY = 0.6
const DEFAULT_INTERVAL_MS = 5000

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

  // Load settings once, then react to changes pushed from the Settings page.
  useEffect(() => {
    void window.omi.rewindGetSettings().then(setSettings)
    return window.omi.onRewindSettings(setSettings)
  }, [])

  useEffect(() => {
    const enabled = !!settings?.captureEnabled
    const intervalMs = settings?.intervalMs ?? DEFAULT_INTERVAL_MS
    let cancelled = false

    const stop = (): void => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }

    const scheduleNext = (): void => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        void runCaptureLoop()
      }, intervalMs)
    }

    const captureOnce = async (): Promise<void> => {
      if (cancelled) return
      const v = videoRef.current
      if (!v || !v.videoWidth || !v.videoHeight || savingRef.current) return
      savingRef.current = true
      try {
        const scale = Math.min(1, MAX_EDGE / Math.max(v.videoWidth, v.videoHeight))
        const w = Math.round(v.videoWidth * scale)
        const h = Math.round(v.videoHeight * scale)
        const canvas = canvasRef.current ?? (canvasRef.current = document.createElement('canvas'))
        if (canvas.width !== w) canvas.width = w
        if (canvas.height !== h) canvas.height = h
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        ctx.drawImage(v, 0, 0, w, h)
        const blob = await new Promise<Blob | null>((r) =>
          canvas.toBlob(r, 'image/jpeg', JPEG_QUALITY)
        )
        if (blob && !cancelled) {
          await window.omi.rewindSaveFrame(new Uint8Array(await blob.arrayBuffer()))
        }
      } catch (e) {
        console.error('[rewind] sample failed:', (e as Error).message)
      } finally {
        savingRef.current = false
      }
    }

    // Self-pacing: schedule the next grab only after the current one settles, so
    // a slow save can never stack concurrent captures.
    const runCaptureLoop = async (): Promise<void> => {
      await captureOnce()
      if (!cancelled) scheduleNext()
    }

    const captureNow = (): void => {
      if (!enabled || cancelled || savingRef.current) return
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      void runCaptureLoop()
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
              // capture on. Keep both low: 720p is enough for a timeline + OCR of
              // normal-size text, and we only sample every few seconds, so 1fps
              // capture is plenty. (Was 1080p@30fps → froze; 1080p@2fps → laggy.)
              maxWidth: 1280,
              maxHeight: 720,
              maxFrameRate: 1
            }
          }
        })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        const v = videoRef.current
        if (v) {
          v.srcObject = stream
          await v.play().catch(() => undefined)
        }
        scheduleNext()
      } catch (e) {
        console.error('[rewind] failed to start capture:', (e as Error).message)
      }
    }

    const offCaptureNow = enabled ? window.omi.onRewindCaptureNow(captureNow) : () => {}

    if (enabled) void start()
    else stop()

    return () => {
      cancelled = true
      offCaptureNow()
      stop()
    }
  }, [settings?.captureEnabled, settings?.intervalMs])

  return (
    <video
      ref={videoRef}
      muted
      className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0"
    />
  )
}
