import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRecording } from './useRecording'
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import { invalidateConversationsCache, refreshCloudConversations } from '../lib/pageCache'
import { createSegmentStore, type SegmentStore } from '../lib/sync/segmentRetention'
import { mergeLanes } from '../lib/sync/mergeLanes'
import { syncLocalConversation } from '../lib/sync/conversationSync'
import type { CaptureSource, LocalConversation, TranscriptLine } from '../../../shared/types'

// How long stop() waits after asking both transcribe-stream lanes to finalize
// before merging — the backend flushes the trailing segment in ~0.3s (3s worst
// case per the PTT budget); this window catches it so the last words spoken
// aren't dropped from the synced conversation.
const FINALIZE_FLUSH_MS = 2_500

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
  // Screen sessions retain each lane's RAW segments (wall-clock stamped) so stop()
  // can merge them into a from-segments POST. Null for mic-only sessions.
  const micStoreRef = useRef<SegmentStore | null>(null)
  const systemStoreRef = useRef<SegmentStore | null>(null)

  // The decorative desktop-video preview lives in the capture window now (it
  // renders nothing here). We just track the picked source id so the capture
  // window can re-open the preview if it restarts mid-session.
  const activeScreenSourceRef = useRef<string | null>(null)

  useEffect(() => {
    return window.omi?.onCaptureEvent?.((ev) => {
      if (ev.type === 'capture-window-restarted' && activeScreenSourceRef.current) {
        window.omi?.captureCommand?.({
          type: 'screen-view',
          active: true,
          sourceId: activeScreenSourceRef.current
        })
      }
    })
  }, [])

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
    // Screen sessions: both lanes ride transcription-only sockets (mode
    // 'transcribe') so the backend's racy per-uid conversation pointer is never
    // in play — the conversation is created client-side on stop. Mic-only stays
    // on /v4/listen (single socket; the server-created conversation is correct).
    const mode = withSystem ? 'transcribe' : 'conversation'
    const sessionStart = Date.now()
    micStoreRef.current = withSystem ? createSegmentStore(sessionStart) : null
    systemStoreRef.current = withSystem ? createSegmentStore(sessionStart) : null
    try {
      micRef.current = await startTranscription(
        'mic',
        {
          onLine: (line) => {
            setMicLines((prev) => [...prev, line])
            setMicInterim('')
          },
          onInterim: setMicInterim,
          onBackend: setMicBackend,
          onError: (e) => console.error('Transcription (mic):', e),
          onSegments: (segs) => micStoreRef.current?.add(segs, Date.now())
        },
        mode
      )
      if (withSystem) {
        systemRef.current = await startTranscription(
          'system',
          {
            onLine: (line) => {
              setSystemLines((prev) => [...prev, line])
              setSystemInterim('')
            },
            onInterim: setSystemInterim,
            onBackend: setSystemBackend,
            onError: (e) => console.error('Transcription (system):', e),
            onSegments: (segs) => systemStoreRef.current?.add(segs, Date.now())
          },
          mode
        )
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
    // The preview stream is opened in the capture window; just hand it the source.
    activeScreenSourceRef.current = s.id
    window.omi?.captureCommand?.({ type: 'screen-view', active: true, sourceId: s.id })
  }

  const stopScreen = (): void => {
    activeScreenSourceRef.current = null
    window.omi?.captureCommand?.({ type: 'screen-view', active: false })
  }

  const stop = async (): Promise<void> => {
    if (hasSystem) {
      // Ask both transcribe-stream lanes to flush their trailing segment, and
      // give it a bounded window to arrive (segments land in the stores via
      // onSegments) before tearing the sockets down.
      setSaving(true)
      micRef.current?.finalize()
      systemRef.current?.finalize()
      await new Promise((r) => setTimeout(r, FINALIZE_FLUSH_MS))
    }
    micRef.current?.stop()
    micRef.current = null
    systemRef.current?.stop()
    systemRef.current = null
    activeScreenSourceRef.current = null
    window.omi?.captureCommand?.({ type: 'screen-view', active: false })

    const session = stopSession()
    if (!session) {
      setSaving(false)
      return
    }

    // Mic-only sessions are backend-owned: /v4/listen creates the titled cloud
    // conversation from the same stream, so saving a local copy would just be an
    // untitled duplicate. Mic sessions just refresh the cloud list.
    if (!hasSystem) {
      refreshCloudConversations()
      navigate('/conversations', { replace: true })
      return
    }

    try {
      const transcript = formatTranscript({
        hasSystem,
        micLines,
        micInterim,
        systemLines,
        systemInterim
      })
      // Merge both lanes' raw segments by wall-clock and queue the row in the
      // sync outbox BEFORE the POST — an offline/failed post stays visible as
      // "sync pending" and retries later (see lib/sync/outbox.ts).
      const segments = mergeLanes(micStoreRef.current?.list() ?? [], systemStoreRef.current?.list() ?? [])
      const conversation: LocalConversation = {
        id: session.conversationId,
        startedAt: session.startedAt,
        endedAt: session.endedAt,
        transcript,
        createdAt: Date.now(),
        syncState: segments.length > 0 ? 'pending' : 'local_only',
        segments
      }
      await window.omi.insertLocalConversation(conversation)
      invalidateConversationsCache()
      navigate(`/conversations/${session.conversationId}`, { replace: true })
      if (segments.length > 0) {
        // Fire-and-forget: the outbox owns retries; the Conversations list
        // reconciles the local row away once the cloud conversation appears.
        void syncLocalConversation(conversation).then((out) => {
          if (out?.status === 'done') {
            refreshCloudConversations()
            window.omi.notifyConversationsChanged()
          }
        })
      }
    } catch (e) {
      console.error('Save failed:', e)
      alert(`Save failed: ${(e as Error).message}`)
    } finally {
      micStoreRef.current = null
      systemStoreRef.current = null
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
    start,
    pickScreen,
    stopScreen,
    stop
  }
}
