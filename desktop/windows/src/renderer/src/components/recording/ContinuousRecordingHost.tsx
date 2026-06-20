import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { startLiveMicSession } from '../../lib/liveMicSession'
import {
  setContinuousRecordingAuth,
  setContinuousRecordingPreference,
  setContinuousRecordingSession
} from '../../lib/continuousRecordingStatus'

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

  useEffect(() => {
    setContinuousRecordingPreference(!!getPreferences().continuousRecording)
    return onPreferencesChange((p) => {
      const next = !!p.continuousRecording
      setEnabled(next)
      setContinuousRecordingPreference(next)
    })
  }, [])
  useEffect(() => {
    setContinuousRecordingAuth({
      signedIn: !!auth.currentUser,
      email: auth.currentUser?.email ?? null
    })
    return onAuthStateChanged(auth, (u) => {
      setSignedIn(!!u)
      setContinuousRecordingAuth({ signedIn: !!u, email: u?.email ?? null })
    })
  }, [])

  useEffect(() => {
    if (!enabled || !signedIn) {
      setContinuousRecordingSession(false)
      return
    }
    setContinuousRecordingSession(true)
    const session = startLiveMicSession()
    return () => {
      setContinuousRecordingSession(false)
      session.stop()
    }
  }, [enabled, signedIn])

  return null
}
