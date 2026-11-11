import { useEffect, useState } from 'react'
import { TriangleAlert, X } from 'lucide-react'

// A subtle, non-blocking banner shown while the backend is in a 429 "storm" (this
// account hits recurring ones). During a storm, background work — task hydrate/
// promote/sync — quietly stops; without this the app just looks frozen. Main
// detects the storm (main/observability/backendDegraded) and broadcasts
// `backend:degraded`; this is the only UI it drives.
//
// Deliberately calm: amber accent (not alarm-red), neutral glass, no modal, no
// action required — it clears itself the moment requests succeed again. Mirrors
// DbRecoveryNotice's top-of-window banner. The dismiss X hides it for the current
// storm; a recovery re-arms it so the next storm shows again.

export function DegradedModeNotice(): React.JSX.Element | null {
  const [degraded, setDegraded] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let alive = true
    // Sync the current state in case a storm was already active when we mounted.
    void window.omi
      .backendDegradedState()
      .then((d) => {
        if (alive) setDegraded(d)
      })
      .catch(() => {
        // A missing/failing channel must never break the app shell.
      })
    const unsubscribe = window.omi.onBackendDegraded((d) => {
      if (!alive) return
      setDegraded(d)
      // Recovery re-arms the dismiss latch so a later storm shows again.
      if (!d) setDismissed(false)
    })
    return () => {
      alive = false
      unsubscribe()
    }
  }, [])

  if (!degraded || dismissed) return null

  return (
    <div
      role="status"
      className="glass mx-4 mt-3 flex items-start gap-3 border border-warning/30 bg-warning/5 px-4 py-3"
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" strokeWidth={1.9} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white/95">Omi is catching up</div>
        <div className="mt-0.5 break-words text-xs leading-relaxed text-white/65">
          Omi&rsquo;s servers are busy. Syncing will resume automatically.
        </div>
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
