import { useEffect } from 'react'
import { startMeetingSession, type MeetingSessionHandle } from './meetingSession'

// Services 'meeting-capture-start' / 'meeting-capture-stop' commands from
// main's meeting monitor, inside the capture window. Module-singleton session
// map keyed by meetingId (same idempotency pattern as AudioSessionHost) so
// StrictMode double-mounts / duplicate commands can't double-start a meeting.
//
// Lifecycle is reported back over the capture-event channel as
// 'meeting-capture-status' — main uses it to keep the toast honest.

type Slot = { handle: MeetingSessionHandle | null; stopped: boolean }
const sessions = new Map<string, Slot>()

function emitStatus(meetingId: string, status: 'started' | 'error' | 'saved', message?: string): void {
  window.omi?.captureEmit({ type: 'meeting-capture-status', meetingId, status, ...(message ? { message } : {}) })
}

async function start(meetingId: string, appName: string): Promise<void> {
  if (sessions.has(meetingId)) return // duplicate command
  const slot: Slot = { handle: null, stopped: false }
  sessions.set(meetingId, slot)
  try {
    const handle = await startMeetingSession({
      appName,
      onError: (message) => emitStatus(meetingId, 'error', message)
    })
    if (slot.stopped) {
      // stop landed while lanes were connecting — finalize immediately.
      await handle.stop()
      sessions.delete(meetingId)
      return
    }
    slot.handle = handle
    emitStatus(meetingId, 'started')
  } catch (e) {
    sessions.delete(meetingId)
    emitStatus(meetingId, 'error', (e as Error).message)
  }
}

async function stop(meetingId: string): Promise<void> {
  const slot = sessions.get(meetingId)
  if (!slot) return
  slot.stopped = true
  if (!slot.handle) return // start() will see `stopped` and finalize
  sessions.delete(meetingId)
  try {
    await slot.handle.stop()
    emitStatus(meetingId, 'saved')
  } catch (e) {
    emitStatus(meetingId, 'error', (e as Error).message)
  }
}

export function MeetingSessionHost(): null {
  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd) => {
      if (cmd.type === 'meeting-capture-start') void start(cmd.meetingId, cmd.appName)
      else if (cmd.type === 'meeting-capture-stop') void stop(cmd.meetingId)
    })
  }, [])
  return null
}
