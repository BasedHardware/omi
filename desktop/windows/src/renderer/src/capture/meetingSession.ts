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
import { isLiveMicSessionActive } from './liveMicSession'
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
}): Promise<MeetingSessionHandle> {
  const startedAt = Date.now()
  const systemLines: TranscriptLine[] = []
  let stopped = false

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
      mode
    )

  // The remote/system side is always captured. The mic lane is opened here only
  // if no continuous mic session already owns the mic (C6) — otherwise we'd open a
  // second, racing /v4/listen for the same audio.
  const lanes: { source: ListenSource; mode: 'conversation' | 'transcribe' }[] = [
    { source: 'system', mode: 'transcribe' }
  ]
  if (!isLiveMicSessionActive()) lanes.push({ source: 'mic', mode: 'conversation' })

  // allSettled (not all): if one lane fails to start, the sibling lane has
  // ALREADY opened its WS + acquired its stream — Promise.all's reject would
  // strand that resolved handle with no reference (a hot mic with no way to
  // stop it). Collect every fulfilled handle so a failure can tear them ALL
  // down before rethrowing.
  const results = await Promise.allSettled(lanes.map((l) => startLane(l.source, l.mode)))
  const handles = results
    .filter((r): r is PromiseFulfilledResult<TranscriptionHandle> => r.status === 'fulfilled')
    .map((r) => r.value)
  const failed = results.find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined
  if (failed) {
    for (const h of handles) {
      try {
        h.stop()
      } catch {
        /* ignore */
      }
    }
    throw failed.reason
  }

  return {
    stop: async (): Promise<void> => {
      if (stopped) return
      stopped = true
      for (const h of handles) {
        try {
          h.stop()
        } catch {
          /* ignore */
        }
      }
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
