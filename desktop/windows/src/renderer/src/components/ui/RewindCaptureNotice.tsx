import { useEffect, useState } from 'react'
import { MonitorX, X } from 'lucide-react'
import type { RewindCaptureDiagnostics } from '../../../../shared/types'

// Shown once, at the top of the main window, when Rewind is enabled but can't
// actually get a screen source. Before this, the failure (desktopCapturer's
// getSources() throwing) surfaced only as a console.error the user never
// sees — Rewind would just never start capturing, silently. Same "make the
// failure honest" spirit as DbRecoveryNotice.
//
// Neutral/white styling only — no purple (INV-UI-1), no alarm-red for what is
// an environment/config gap, not data loss.

export function RewindCaptureNotice(): React.JSX.Element | null {
  const [captureEnabled, setCaptureEnabled] = useState(false)
  const [diagnostics, setDiagnostics] = useState<RewindCaptureDiagnostics | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let alive = true
    void window.omi
      .rewindGetSettings()
      .then((s) => {
        if (alive) setCaptureEnabled(s.captureEnabled)
      })
      .catch(() => {
        // A missing/failing settings channel must never break the app shell.
      })
    void window.omi
      .rewindCaptureDiagnostics()
      .then((d) => {
        if (alive) setDiagnostics(d)
      })
      .catch(() => {
        // A missing/failing diagnostics channel must never break the app shell.
      })
    return () => {
      alive = false
    }
  }, [])

  // Only relevant when the user actually wants Rewind on — showing this to
  // someone who has it off would just be irrelevant noise.
  if (dismissed || !captureEnabled || !diagnostics || diagnostics.available) return null

  const body = diagnostics.likelyMissingLinuxPortal
    ? "Your Linux desktop doesn't have a working screen-sharing portal for this " +
      "compositor, so Omi can't get a screen source. Install a matching " +
      'xdg-desktop-portal backend (e.g. xdg-desktop-portal-wlr for niri/Sway/' +
      "Hyprland), make sure it's preferred for ScreenCast, then restart Omi."
    : `Omi couldn't get a screen source${diagnostics.reason ? ` (${diagnostics.reason})` : ''}. ` +
      'Recording will stay off until this is resolved.'

  return (
    <div
      role="status"
      className="glass mx-4 mt-3 flex items-start gap-3 border border-white/15 px-4 py-3"
    >
      <MonitorX className="mt-0.5 h-4 w-4 shrink-0 text-white/85" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white/95">Screen recording isn&apos;t working</div>
        <div className="mt-0.5 break-words text-xs leading-relaxed text-white/65">{body}</div>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="-mr-1 -mt-1 rounded-md p-1 text-white/45 hover:bg-white/10 hover:text-white"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
