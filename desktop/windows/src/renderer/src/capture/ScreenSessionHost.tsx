import { useEffect, useRef, useState } from 'react'

// The decorative desktop-video stream for screen-record mode, moved into the
// capture window. It keeps a getUserMedia desktop stream alive in a hidden
// <video> while a screen session is active; nothing renders it (the mode's actual
// transcription uses mic + system-audio lanes). Driven by 'screen-view' commands:
// active with the user-picked sourceId (falls back to the primary screen).

async function getDesktopStream(sourceId: string): Promise<MediaStream> {
  return (
    navigator.mediaDevices as unknown as {
      getUserMedia: (c: unknown) => Promise<MediaStream>
    }
  ).getUserMedia({
    audio: false,
    video: {
      mandatory: {
        chromeMediaSource: 'desktop',
        chromeMediaSourceId: sourceId,
        maxWidth: 1920,
        maxHeight: 1080
      }
    }
  })
}

export function ScreenSessionHost(): React.JSX.Element {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [req, setReq] = useState<{ active: boolean; sourceId?: string }>({ active: false })

  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd) => {
      if (cmd.type === 'screen-view') setReq({ active: cmd.active, sourceId: cmd.sourceId })
    })
  }, [])

  useEffect(() => {
    let cancelled = false
    const stop = (): void => {
      streamRef.current?.getTracks().forEach((t) => t.stop())
      streamRef.current = null
      if (videoRef.current) videoRef.current.srcObject = null
    }
    const start = async (): Promise<void> => {
      try {
        const sourceId = req.sourceId ?? (await window.omi.rewindPrimarySourceId()) ?? ''
        if (!sourceId || cancelled) return
        const stream = await getDesktopStream(sourceId)
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
      } catch (e) {
        console.error('[capture] screen preview failed:', (e as Error).message)
      }
    }
    if (req.active) void start()
    else stop()
    return () => {
      cancelled = true
      stop()
    }
  }, [req.active, req.sourceId])

  return (
    <video
      ref={videoRef}
      muted
      className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0"
    />
  )
}
