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
//
// LOCAL-SAVE POLICY (matches useRecorder's screen path exactly): the mic lane is
// backend-owned — the cloud creates its own titled conversation from that
// stream — so the local "Meeting" row saves ONLY the system-audio (remote-side)
// transcript. Saving mic lines too would duplicate the mic transcript (once
// server-side, once local). Note for Phase 3: if the continuous-mic session is
// already running, this mic lane opens a SECOND concurrent /v4/listen mic
// session for the same audio (same overlap the manual screen recorder already
// has); the from-segments sync flow that replaces this body resolves it.
// ───────────────────────────────────────────────────────────────────────────
import { startTranscription, type TranscriptionHandle } from '../lib/transcriptionClient'
import type { TranscriptLine } from '../../../shared/types'

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
  // main-process /v4/listen WS and issues the audio-start command that
  // AudioSessionHost (this window) services with a VAD-gated stream — the mic
  // lane feeds the backend's own conversation pipeline, the system lane
  // carries the meeting's remote side (the only one we save locally).
  const startLane = (source: 'mic' | 'system'): Promise<TranscriptionHandle> =>
    startTranscription(source, {
      onLine: (line) => {
        if (!stopped && source === 'system') systemLines.push(line)
      },
      onInterim: () => {},
      onBackend: () => {},
      onError: (e) => {
        console.warn(`[meeting-session] ${source} lane error:`, e.message)
        if (!stopped) args.onError(`${source}: ${e.message}`)
      }
    })

  // allSettled (not all): if one lane fails to start, the sibling lane has
  // ALREADY opened its WS + acquired its stream — Promise.all's reject would
  // strand that resolved handle with no reference (a hot mic with no way to
  // stop it). Collect every fulfilled handle so a failure can tear them ALL
  // down before rethrowing.
  const results = await Promise.allSettled([startLane('mic'), startLane('system')])
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
