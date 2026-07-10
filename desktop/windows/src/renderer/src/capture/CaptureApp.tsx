import { useEffect, useRef } from 'react'
import { RewindCaptureHost } from '../components/rewind/RewindCaptureHost'
import { ContinuousSessionHost } from './ContinuousSessionHost'
import { AudioSessionHost } from './AudioSessionHost'
import { PttCaptureHost } from './PttCaptureHost'
import { ScreenSessionHost } from './ScreenSessionHost'
import { auth } from '../lib/firebase'

// Root of the hidden capture window (renderer #/capture). No visible UI — it only
// mounts the capture hosts that own ALL capture: Rewind frames, the continuous
// mic session, on-demand audio sessions (screen mode), push-to-talk, and the
// decorative screen-preview stream.
//
// It also self-heals its Firebase auth. Firebase doesn't push a fresh sign-in
// across windows in real time, so when the main window's auth transitions it
// sends 'auth-changed' with its current state; if this window's in-memory auth
// disagrees, we reload (after a 1s debounce, re-checking in case Firebase caught
// up on its own) so the persisted session is restored and the listen-WS auth is
// fresh.
export function CaptureApp(): React.JSX.Element {
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return window.omi?.onCaptureCommand?.((cmd) => {
      if (cmd.type !== 'auth-changed') return
      // Compare the actual uid, not just signed-in-ness: an account SWITCH
      // (user A → user B) leaves both sides "signed in" but must still reload so
      // this window's listen-WS auth points at the new user.
      const localUid = auth.currentUser?.uid ?? null
      if (localUid === cmd.uid) {
        if (reloadTimer.current) {
          clearTimeout(reloadTimer.current)
          reloadTimer.current = null
        }
        return
      }
      if (reloadTimer.current) return
      reloadTimer.current = setTimeout(() => {
        reloadTimer.current = null
        if ((auth.currentUser?.uid ?? null) !== cmd.uid) window.location.reload()
      }, 1000)
    })
  }, [])

  return (
    <>
      <RewindCaptureHost />
      <ContinuousSessionHost />
      <AudioSessionHost />
      <PttCaptureHost />
      <ScreenSessionHost />
    </>
  )
}
