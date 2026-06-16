import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRecording } from './useRecording'
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import { invalidateConversationsCache, refreshCloudConversations } from '../lib/pageCache'
import type { CaptureSource, TranscriptLine } from '../../../shared/types'

function linesToString(lines: TranscriptLine[], interim: string): string {
  const parts = lines.map((l) => (l.speaker ? `${l.speaker}: ${l.text}` : l.text))
  if (interim) parts.push(interim)
  return parts.join('\n').trim()
}

function formatTranscript(args: {
  hasSystem: boolean
  micLines: TranscriptLine[]
  micInterim: string
  systemLines: TranscriptLine[]
  systemInterim: string
}): string {
  const mic = linesToString(args.micLines, args.micInterim)
  const system = linesToString(args.systemLines, args.systemInterim)
  if (!args.hasSystem) return mic
  const blocks: string[] = []
  if (mic) blocks.push(`Microphone:\n${mic}`)
  if (system) blocks.push(`System audio:\n${system}`)
  return blocks.join('\n\n')
}

export type UseRecorder = {
  recording: boolean
  saving: boolean
  /** Finalized lines for the mic. Each line has an optional speaker label when
   * provided by v4/listen. */
  micLines: TranscriptLine[]
  /** Current in-progress (interim) mic text. The v4/listen path leaves this empty. */
  micInterim: string
  /** System-audio lines, populated only in 'screen' mode. */
  systemLines: TranscriptLine[]
  systemInterim: string
  /** Which backend is driving the mic (and system) session, for debug/UI hints.
   * Always 'omi' once connected (the only transcription backend). */
  micBackend: 'omi' | null
  systemBackend: 'omi' | null
  screenStream: MediaStream | null
  videoRef: React.RefObject<HTMLVideoElement | null>
  /** Begin a recording session. Pass `system: true` to also transcribe loopback. */
  start: (opts?: { system?: boolean }) => Promise<void>
  pickScreen: (s: CaptureSource) => Promise<void>
  stopScreen: () => void
  stop: () => Promise<void>
}

export function useRecorder(): UseRecorder {
  const navigate = useNavigate()
  const { state, start: startSession, stop: stopSession } = useRecording()
  const [micLines, setMicLines] = useState<TranscriptLine[]>([])
  const [micInterim, setMicInterim] = useState('')
  const [systemLines, setSystemLines] = useState<TranscriptLine[]>([])
  const [systemInterim, setSystemInterim] = useState('')
  const [hasSystem, setHasSystem] = useState(false)
  const [micBackend, setMicBackend] = useState<'omi' | null>(null)
  const [systemBackend, setSystemBackend] = useState<'omi' | null>(null)
  const [saving, setSaving] = useState(false)
  const micRef = useRef<TranscriptionHandle | null>(null)
  const systemRef = useRef<TranscriptionHandle | null>(null)

  const [screenStream, setScreenStream] = useState<MediaStream | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // Attach/detach the MediaStream when screenStream changes. We can't do this
  // imperatively inside pickScreen() because the <video> element is
  // conditionally rendered — videoRef.current is null until React re-renders.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (screenStream) {
      v.srcObject = screenStream
      v.play().catch((e) => console.error('Video play failed:', e))
    } else {
      v.srcObject = null
    }
  }, [screenStream])

  const start = async (opts?: { system?: boolean }): Promise<void> => {
    const withSystem = opts?.system ?? false
    startSession()
    setMicLines([])
    setMicInterim('')
    setSystemLines([])
    setSystemInterim('')
    setMicBackend(null)
    setSystemBackend(null)
    setHasSystem(withSystem)
    try {
      micRef.current = await startTranscription('mic', {
        onLine: (line) => {
          setMicLines((prev) => [...prev, line])
          setMicInterim('')
        },
        onInterim: setMicInterim,
        onBackend: setMicBackend,
        onError: (e) => console.error('Transcription (mic):', e)
      })
      if (withSystem) {
        systemRef.current = await startTranscription('system', {
          onLine: (line) => {
            setSystemLines((prev) => [...prev, line])
            setSystemInterim('')
          },
          onInterim: setSystemInterim,
          onBackend: setSystemBackend,
          onError: (e) => console.error('Transcription (system):', e)
        })
      }
    } catch (e) {
      micRef.current?.stop()
      micRef.current = null
      systemRef.current?.stop()
      systemRef.current = null
      const err = e as Error
      const hint =
        err.name === 'NotAllowedError'
          ? withSystem
            ? '\n\nWindows blocked microphone or system-audio capture. Open Settings → Privacy & security → Microphone and allow this app.'
            : '\n\nWindows blocked microphone access. Open Settings → Privacy & security → Microphone and allow this app.'
          : ''
      alert(`Recording failed: ${err.message}${hint}`)
      stopSession()
    }
  }

  const pickScreen = async (s: CaptureSource): Promise<void> => {
    try {
      const stream = await (
        navigator.mediaDevices as unknown as {
          getUserMedia: (c: unknown) => Promise<MediaStream>
        }
      ).getUserMedia({
        audio: false,
        video: {
          mandatory: {
            chromeMediaSource: 'desktop',
            chromeMediaSourceId: s.id,
            minWidth: 640,
            maxWidth: 1920,
            minHeight: 360,
            maxHeight: 1080
          }
        }
      })
      setScreenStream(stream)
    } catch (e) {
      const err = e as Error
      const hint =
        err.name === 'NotAllowedError'
          ? '\n\nWindows blocked screen capture. Open Settings → Privacy & security and allow desktop apps to access screen recording.'
          : ''
      alert(`Screen capture failed: ${err.message}${hint}`)
    }
  }

  const stopScreen = (): void => {
    screenStream?.getTracks().forEach((t) => t.stop())
    setScreenStream(null)
    if (videoRef.current) videoRef.current.srcObject = null
  }

  const stop = async (): Promise<void> => {
    micRef.current?.stop()
    micRef.current = null
    systemRef.current?.stop()
    systemRef.current = null
    screenStream?.getTracks().forEach((t) => t.stop())
    setScreenStream(null)
    if (videoRef.current) videoRef.current.srcObject = null

    const session = stopSession()
    if (!session) return

    // Mic-only sessions are backend-owned now: the cloud creates a titled
    // conversation from the same stream, so saving a local copy would just be an
    // untitled duplicate. Only screen sessions (which carry their own system-audio
    // transcript) still save locally. Mic sessions just refresh the cloud list.
    if (!hasSystem) {
      refreshCloudConversations()
      navigate('/conversations', { replace: true })
      return
    }

    setSaving(true)
    try {
      const transcript = formatTranscript({
        hasSystem,
        micLines,
        micInterim,
        systemLines,
        systemInterim
      })
      await window.omi.insertLocalConversation({
        id: session.conversationId,
        startedAt: session.startedAt,
        endedAt: session.endedAt,
        transcript,
        createdAt: Date.now()
      })
      // Saved locally only (the dev API key 401s on Omi's read/reprocess
      // endpoints, so a pushed copy dead-ends). Cloud conversations are still
      // read from Omi elsewhere.
      invalidateConversationsCache()
      navigate(`/conversations/${session.conversationId}`, { replace: true })
    } catch (e) {
      console.error('Save failed:', e)
      alert(`Save failed: ${(e as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  return {
    recording: state !== 'idle',
    saving,
    micLines,
    micInterim,
    systemLines,
    systemInterim,
    micBackend,
    systemBackend,
    screenStream,
    videoRef,
    start,
    pickScreen,
    stopScreen,
    stop
  }
}
