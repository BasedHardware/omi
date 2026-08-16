import { useEffect } from 'react'
import { startMeetingSession, type MeetingSessionHandle } from './meetingSession'

// Services 'meeting-capture-start' / 'meeting-capture-stop' commands from
// main's meeting monitor, inside the capture window. Module-singleton session
// map keyed by meetingId (same idempotency pattern as AudioSessionHost) so
// StrictMode double-mounts / duplicate commands can't double-start a meeting.
//
// Lifecycle is reported back over the capture-event channel as
// 'meeting-capture-status' — main uses it to keep the toast honest.

type Slot = {
  meetingId: string
  attemptId: number
  handle: MeetingSessionHandle | null
  abort: AbortController
  stopped: boolean
  errorReported: boolean
  pendingStartupError: string | null
}
const sessions = new Map<number, Slot>()

function emitStatus(
  meetingId: string,
  attemptId: number,
  status: 'started' | 'startup-error' | 'runtime-error' | 'saved' | 'save-error',
  message?: string
): void {
  window.omi?.captureEmit({
    type: 'meeting-capture-status',
    meetingId,
    attemptId,
    status,
    ...(message ? { message } : {})
  })
}

async function start(meetingId: string, attemptId: number, appName: string): Promise<void> {
  if (sessions.has(attemptId)) return // duplicate command
  const slot: Slot = {
    meetingId,
    attemptId,
    handle: null,
    abort: new AbortController(),
    stopped: false,
    errorReported: false,
    pendingStartupError: null
  }
  sessions.set(attemptId, slot)
  const reportRuntimeError = (message: string): void => {
    if (slot.stopped || slot.errorReported || sessions.get(attemptId) !== slot) return
    slot.errorReported = true
    emitStatus(meetingId, attemptId, 'runtime-error', message)
  }
  try {
    const handle = await startMeetingSession({
      appName,
      // Startup failures reject startMeetingSession after every sibling lane has
      // settled and been cleaned up. A lane can still drop after becoming ready
      // while its sibling is starting, so hold that early error until the startup
      // handle exists and can be torn down.
      onError: (message) => {
        if (slot.handle) reportRuntimeError(message)
        else slot.pendingStartupError ??= message
      },
      signal: slot.abort.signal
    })
    if (slot.stopped) {
      // stop landed while lanes were connecting — finalize immediately.
      await handle.stop()
      sessions.delete(attemptId)
      return
    }
    if (slot.pendingStartupError) {
      slot.stopped = true
      try {
        await handle.stop()
      } catch {
        /* the original startup failure remains the actionable error */
      }
      sessions.delete(attemptId)
      emitStatus(meetingId, attemptId, 'startup-error', slot.pendingStartupError)
      return
    }
    slot.handle = handle
    emitStatus(meetingId, attemptId, 'started')
  } catch (e) {
    if (!slot.stopped) {
      emitStatus(meetingId, attemptId, 'startup-error', (e as Error).message)
    }
    sessions.delete(attemptId)
  }
}

async function stop(meetingId: string, attemptId: number): Promise<void> {
  const slot = sessions.get(attemptId)
  if (!slot || slot.meetingId !== meetingId) return
  slot.stopped = true
  slot.abort.abort()
  if (!slot.handle) return // start() will see `stopped` and finalize
  sessions.delete(attemptId)
  try {
    await slot.handle.stop()
    emitStatus(meetingId, attemptId, 'saved')
  } catch (e) {
    emitStatus(meetingId, attemptId, 'save-error', (e as Error).message)
  }
}

export function MeetingSessionHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd) => {
      if (cmd.type === 'meeting-capture-start')
        void start(cmd.meetingId, cmd.attemptId, cmd.appName)
      else if (cmd.type === 'meeting-capture-stop') void stop(cmd.meetingId, cmd.attemptId)
    })
  }, [])
  return null
}
