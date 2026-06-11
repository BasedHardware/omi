import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { startLiveMicSession } from '../../lib/liveMicSession'

// Always-on microphone capture. Mounted once in the authed app shell (like
// RewindCaptureHost) so it runs regardless of the active tab. When the
// `continuousRecording` preference is on AND a user is signed in, it owns the
// shared mic → /v4/listen session (via startLiveMicSession); the backend stores
// each conversation and the list/live view show it. The session lifecycle —
// connect/retry, 30s-silence + "Save now" finalize, boundary handling, polling —
// all lives in startLiveMicSession, shared with the one-off LiveConversation view.
export function ContinuousRecordingHost(): React.JSX.Element | null {
  const [enabled, setEnabled] = useState(() => !!getPreferences().continuousRecording)
  const [signedIn, setSignedIn] = useState(() => !!auth.currentUser)

  useEffect(() => onPreferencesChange((p) => setEnabled(!!p.continuousRecording)), [])
  useEffect(() => onAuthStateChanged(auth, (u) => setSignedIn(!!u)), [])

  useEffect(() => {
    if (!enabled || !signedIn) return
    const session = startLiveMicSession()
    return () => session.stop()
  }, [enabled, signedIn])

  return null
}
