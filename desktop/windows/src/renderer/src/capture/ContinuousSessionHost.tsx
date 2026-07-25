import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { getPreferences, onPreferencesChange } from '../lib/preferences'
import { liveConversation, requestFinalize } from '../lib/liveConversation'
import { formatAssistantLine, shouldInjectIntoLive } from '../lib/voice/injectedTranscript'
import { startLiveMicSession } from './liveMicSession'
import { captureLiveStore } from './liveStore'

// Owns the always-on mic → /v4/listen session, INSIDE the capture window (moved
// from the app-shell ContinuousRecordingHost). It runs the session when either:
//   - the continuousRecording preference is on (macOS-faithful always-on), OR
//   - a UI LiveConversation view is open (live-view refcount > 0) — so "New" still
//     captures a one-off session even when continuous recording is off.
// ...and a user is signed in. Only ONE session runs at a time (the boolean
// `shouldRun` gates a single startLiveMicSession).
//
// The refcount is driven by 'live-view' commands the UI view sends on mount/
// unmount; 'live-finalize' ("Save now") is forwarded here and notifies the local
// finalize subscriber (the running session).
export function ContinuousSessionHost(): null {
  const [enabled, setEnabled] = useState(() => !!getPreferences().continuousRecording)
  const [signedIn, setSignedIn] = useState(() => !!auth.currentUser)
  const [liveViews, setLiveViews] = useState(0)

  useEffect(() => onPreferencesChange((p) => setEnabled(!!p.continuousRecording)), [])
  useEffect(() => onAuthStateChanged(auth, (u) => setSignedIn(!!u)), [])

  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd) => {
      if (cmd.type === 'live-view') {
        setLiveViews((n) => Math.max(0, n + (cmd.active ? 1 : -1)))
      } else if (cmd.type === 'live-finalize') {
        // In the capture window requestFinalize notifies the local subscriber (the
        // running liveMicSession), which ends → stores → restarts the session.
        requestFinalize()
      } else if (cmd.type === 'assistant-utterance') {
        // Echo gate companion (Phase 6): while the gate pauses the feed, Omi's
        // spoken words still belong in the record — injected from SOURCE text,
        // never re-transcribed. Only when a session is actually running (a line
        // injected into a dead store would leak into the next session's view).
        if (shouldInjectIntoLive(liveConversation.getStatus())) {
          const line = formatAssistantLine(cmd.text, cmd.utteranceId)
          if (line) captureLiveStore.appendLine(line)
        }
      }
    })
  }, [])

  const shouldRun = signedIn && (enabled || liveViews > 0)
  useEffect(() => {
    if (!shouldRun) return
    const session = startLiveMicSession()
    return () => session.stop()
  }, [shouldRun])

  return null
}
