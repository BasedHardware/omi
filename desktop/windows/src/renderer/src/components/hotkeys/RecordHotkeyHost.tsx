import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth } from '../../lib/firebase'

// Receives the global mic record chord (default Ctrl+Space) from main and acts on
// it. Main sends 'recorder:hotkey' with the capture mode after surfacing the
// window; a 'mic' press opens the live mic-recording view (the same action the old
// record-menu's "Mic only" option performed). Other modes are ignored — screen
// capture starts from the in-app control, not a global chord. Renders nothing;
// mounted once at the app root next to TrayStateHost.
export function RecordHotkeyHost(): null {
  const navigate = useNavigate()

  useEffect(() => {
    return window.omi?.onRecordHotkey?.((choice) => {
      // Only act while signed in — the live view needs an authed session.
      if (choice === 'mic' && auth.currentUser) navigate('/conversations/live')
    })
  }, [navigate])

  return null
}
