import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, setPreferences, onPreferencesChange } from '../../lib/preferences'

// Keeps the system-tray icon/menu in sync with the app's listening state, and
// lets the tray drive it. Mounted once at the app root (outside the auth gate) so
// it can report 'idle' while signed out as well as 'listening'/'paused' once
// signed in. State is derived from the continuousRecording preference + auth:
//   signed out            → 'idle'
//   signed in, listening  → 'listening'
//   signed in, paused     → 'paused'
// The tray's "toggle listening" action flips the continuousRecording pref, which
// starts/stops the ContinuousRecordingHost session and re-reports the new state.
export function TrayStateHost(): null {
  const [enabled, setEnabled] = useState(() => !!getPreferences().continuousRecording)
  const [signedIn, setSignedIn] = useState(() => !!auth.currentUser)

  useEffect(() => onPreferencesChange((p) => setEnabled(!!p.continuousRecording)), [])
  useEffect(() => onAuthStateChanged(auth, (u) => setSignedIn(!!u)), [])

  // Report the current state to main on mount and whenever it changes.
  useEffect(() => {
    const state = !signedIn ? 'idle' : enabled ? 'listening' : 'paused'
    window.omi?.trayReportState?.(state)
  }, [enabled, signedIn])

  // The tray menu / icon click toggles listening. Flip the pref (the effect above
  // then re-reports, and ContinuousRecordingHost starts/stops the session).
  useEffect(() => {
    return window.omi?.onTrayToggleListening?.(() => {
      setPreferences({ continuousRecording: !getPreferences().continuousRecording })
    })
  }, [])

  // Tray menu → Settings: main surfaces the window and asks us to navigate.
  const navigate = useNavigate()
  useEffect(() => {
    return window.omi?.onTrayOpenSettings?.(() => navigate('/settings'))
  }, [navigate])

  return null
}
