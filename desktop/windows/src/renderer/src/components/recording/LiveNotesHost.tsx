import { useEffect } from 'react'
import { liveNotesMonitor } from '../../lib/liveNotes/liveNotesMonitor'

// Mounts the LiveNotes monitor at the app-shell root (next to LiveMirrorHost),
// so AI note generation runs off the live transcript whenever the main window is
// open — regardless of whether the notes PANEL (the /conversations/live split) is
// open. Renders nothing; the panel subscribes to the monitor separately. The
// monitor refcounts start()/stop() so React StrictMode's double-mount subscribes
// exactly once.
export function LiveNotesHost(): null {
  useEffect(() => liveNotesMonitor.start(), [])
  return null
}
