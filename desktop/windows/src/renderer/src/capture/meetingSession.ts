// One auto-captured meeting session (mic + system-audio lanes), running INSIDE
// the capture window — started/stopped by main's meeting monitor via
// 'meeting-capture-start' / 'meeting-capture-stop' commands.
//
// LANE WIRING (matches useRecorder's screen path):
//  - System (remote) lane: transcription-only ('transcribe'). It is saved LOCALLY
//    only, so it never needs a server-side conversation — riding transcribe-stream
//    keeps it out of the backend's racy per-uid /v4/listen conversation pointer,
//    the same reason the screen recorder uses 'transcribe' for its system lane.
//  - Mic lane: backend-owned /v4/listen ('conversation') — the cloud creates its
//    own titled conversation from the mic stream. Opened here ONLY when no
//    continuous mic session is already running.
//
// C6 (double mic-session race): if the always-on continuous mic session is
// running, it ALREADY streams the mic to /v4/listen. Opening a second mic
// /v4/listen for the same audio spawns a duplicate, racing conversation socket
// (the backend coalesces same-uid conversation sockets). So the mic lane DEFERS
// to the continuous session when `isLiveMicSessionActive()` — the meeting then
// captures only the remote/system side. When nothing else owns the mic, the
// meeting opens the mic lane itself.
//
// LOCAL-SAVE POLICY: the local "Meeting" row saves ONLY the system-audio
// (remote-side) transcript. The mic side is backend-owned (its own cloud
// conversation, via either the continuous session or this meeting's mic lane), so
// saving mic lines here too would duplicate it.
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import {
  getLiveMicSessionHealth,
  onLiveMicSessionHealth,
  waitForLiveMicSessionReady
} from './liveMicSession'
import type { ListenSource, TranscriptLine } from '../../../shared/types'

export type MeetingSessionHandle = {
  /** Finalize: stop both lanes and save the conversation. Resolves when saved. */
  stop: () => Promise<void>
}

/** The local "Meeting" conversation carries the system-audio (remote-side)
 *  transcript only; the mic lane is backend-owned (its own cloud conversation),
 *  so including mic lines here would duplicate them. */
export function formatMeetingTranscript(system: TranscriptLine[]): string {
  return system
    .map((l) => (l.speaker ? `${l.speaker}: ${l.text}` : l.text))
    .join('\n')
    .trim()
}

export async function startMeetingSession(args: {
  appName: string
  onError: (message: string) => void
  signal?: AbortSignal
}): Promise<MeetingSessionHandle> {
  const startedAt = Date.now()
  const systemLines: TranscriptLine[] = []
  let stopped = args.signal?.aborted ?? false
  const startingHandles = new Set<TranscriptionHandle>()

  const stopStartingHandles = (): void => {
    stopped = true
    for (const handle of startingHandles) {
      try {
        handle.stop()
      } catch {
        /* ignore */
      }
    }
  }
  args.signal?.addEventListener('abort', stopStartingHandles, { once: true })

  // Both lanes ride the normal capture path: startTranscription opens the
  // main-process listen WS and issues the audio-start command that
  // AudioSessionHost (this window) services with a VAD-gated stream. The system
  // lane is transcription-only ('transcribe') and saved locally; the mic lane is
  // backend-owned ('conversation').
  const startLane = (
    source: ListenSource,
    mode: 'conversation' | 'transcribe'
  ): Promise<TranscriptionHandle> =>
    startTranscription(
      source,
      {
        onLine: (line) => {
          if (!stopped && source === 'system') systemLines.push(line)
        },
        onInterim: () => {},
        onBackend: () => {},
        onError: (e) => {
          console.warn(`[meeting-session] ${source} lane error:`, e.message)
          if (!stopped) args.onError(`${source}: ${e.message}`)
        }
      },
      mode,
      undefined,
      args.signal
    ).then((handle) => {
      if (stopped) {
        handle.stop()
        const error = new Error('Meeting capture startup cancelled')
        error.name = 'AbortError'
        throw error
      }
      startingHandles.add(handle)
      return handle
    })

  // The remote/system side is always captured. The mic lane is opened here only
  // if no continuous mic session already owns the mic (C6) — otherwise we'd open a
  // second, racing /v4/listen for the same audio.
  const starts: Promise<TranscriptionHandle | null>[] = [startLane('system', 'transcribe')]
  const liveMicHealth = getLiveMicSessionHealth()
  const delegatedMic = liveMicHealth === 'connecting' || liveMicHealth === 'ready'
  if (liveMicHealth === 'connecting') {
    starts.push(
      waitForLiveMicSessionReady(args.signal).then((ready) => {
        if (!ready) throw new Error('continuous microphone transcription did not become ready')
        return null
      })
    )
  } else if (liveMicHealth !== 'ready') {
    starts.push(startLane('mic', 'conversation'))
  }

  // allSettled (not all): if one lane fails to start, the sibling lane has
  // ALREADY opened its WS + acquired its stream — Promise.all's reject would
  // strand that resolved handle with no reference (a hot mic with no way to
  // stop it). Collect every fulfilled handle so a failure can tear them ALL
  // down before rethrowing.
  const results = await Promise.allSettled(starts)
  const failed = results.find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined
  if (failed) {
    stopStartingHandles()
    args.signal?.removeEventListener('abort', stopStartingHandles)
    throw failed.reason
  }
  if (delegatedMic && getLiveMicSessionHealth() !== 'ready') {
    stopStartingHandles()
    args.signal?.removeEventListener('abort', stopStartingHandles)
    throw new Error('continuous microphone transcription did not remain ready')
  }
  args.signal?.removeEventListener('abort', stopStartingHandles)
  const offLiveMicHealth = delegatedMic
    ? onLiveMicSessionHealth((health) => {
        if (!stopped && health !== 'ready') {
          args.onError('microphone: continuous transcription stopped')
        }
      })
    : () => {}

  return {
    stop: async (): Promise<void> => {
      if (stopped) return
      stopStartingHandles()
      offLiveMicHealth()
      const transcript = formatMeetingTranscript(systemLines)
      // Nothing on the system lane worth saving (mic already went to the
      // backend's own conversation pipeline) — skip the empty row.
      if (!transcript) return
      await window.omi.insertLocalConversation({
        id: `local-${crypto.randomUUID()}`,
        startedAt,
        endedAt: Date.now(),
        transcript: `Meeting (${args.appName})\n\n${transcript}`,
        createdAt: Date.now()
      })
      window.omi.notifyConversationsChanged()
    }
  }
}
