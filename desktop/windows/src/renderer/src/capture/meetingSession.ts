// One auto-captured meeting session (mic + system-audio lanes), running INSIDE
// the capture window — started/stopped by main's meeting monitor via
// 'meeting-capture-start' / 'meeting-capture-stop' commands.
//
// ─── PHASE 3 INTEGRATION SEAM ──────────────────────────────────────────────
// `startMeetingSession` is the single adapter between meeting detection and
// the capture stack. It currently drives the SAME session APIs the UI's
// screen-record mode uses (startTranscription → startOmiListen → audio-start
// commands for the mic + system lanes) and saves a local conversation on stop,
// mirroring useRecorder's screen path. When feat/windows-conv-sync (Phase 3)
// lands, swap THIS FUNCTION's body for the screen-session from-segments sync
// flow — the meeting monitor, command protocol, and MeetingSessionHost do not
// change. One function, one call site.
// ───────────────────────────────────────────────────────────────────────────
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import type { TranscriptLine } from '../../../shared/types'

export type MeetingSessionHandle = {
  /** Finalize: stop both lanes and save the conversation. Resolves when saved. */
  stop: () => Promise<void>
}

function linesToString(lines: TranscriptLine[]): string {
  return lines
    .map((l) => (l.speaker ? `${l.speaker}: ${l.text}` : l.text))
    .join('\n')
    .trim()
}

/** Same two-block shape as useRecorder's screen-mode transcript, so meeting
 *  conversations look identical to manually recorded ones. */
export function formatMeetingTranscript(mic: TranscriptLine[], system: TranscriptLine[]): string {
  const blocks: string[] = []
  const m = linesToString(mic)
  const s = linesToString(system)
  if (m) blocks.push(`Microphone:\n${m}`)
  if (s) blocks.push(`System audio:\n${s}`)
  return blocks.join('\n\n')
}

export async function startMeetingSession(args: {
  appName: string
  onError: (message: string) => void
}): Promise<MeetingSessionHandle> {
  const startedAt = Date.now()
  const micLines: TranscriptLine[] = []
  const systemLines: TranscriptLine[] = []
  let stopped = false

  // Both lanes ride the normal capture path: startTranscription opens the
  // main-process /v4/listen WS and issues the audio-start command that
  // AudioSessionHost (this window) services with a VAD-gated stream — the mic
  // lane feeds the backend's own conversation pipeline, the system lane
  // carries the meeting's remote side.
  let micHandle: TranscriptionHandle | null = null
  let systemHandle: TranscriptionHandle | null = null
  const startLane = (
    source: 'mic' | 'system',
    sink: TranscriptLine[]
  ): Promise<TranscriptionHandle> =>
    startTranscription(source, {
      onLine: (line) => {
        if (!stopped) sink.push(line)
      },
      onInterim: () => {},
      onBackend: () => {},
      onError: (e) => {
        console.warn(`[meeting-session] ${source} lane error:`, e.message)
        if (!stopped) args.onError(`${source}: ${e.message}`)
      }
    })

  try {
    ;[micHandle, systemHandle] = await Promise.all([
      startLane('mic', micLines),
      startLane('system', systemLines)
    ])
  } catch (e) {
    micHandle?.stop()
    systemHandle?.stop()
    throw e
  }

  return {
    stop: async (): Promise<void> => {
      if (stopped) return
      stopped = true
      try {
        micHandle?.stop()
      } catch {
        /* ignore */
      }
      try {
        systemHandle?.stop()
      } catch {
        /* ignore */
      }
      const transcript = formatMeetingTranscript(micLines, systemLines)
      // Nothing worth saving (mic-only chatter already went to the backend's
      // own conversation pipeline via the mic lane) — skip the empty row.
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
