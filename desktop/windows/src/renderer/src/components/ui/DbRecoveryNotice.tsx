import { useEffect, useState } from 'react'
import { DatabaseBackup, X } from 'lucide-react'
import type { DbRecoveryStatus } from '../../../../shared/types'

// Shown once, at the top of the main window, when omi.db was found corrupt at
// startup and repaired. macOS declares a didRecoverFromCorruption flag but never
// sets it, so its recovery UI is unreachable — the user is silently left with a
// wiped database. This is the surface that makes ours honest.
//
// Deliberately calm: the repair already happened and there is nothing for the
// user to do. It states what was kept (or that a reset was unavoidable) and that
// the old file was archived. Neutral/white styling only — no purple (INV-UI-1),
// no alarm-red for what is a successful heal.

function describe(s: DbRecoveryStatus): { title: string; body: string } {
  if (s.reset) {
    return {
      title: 'Omi reset its local database',
      body:
        'It was damaged beyond repair, so Omi started a fresh one. ' +
        'A copy of the old file was saved, and anything synced to your account will load again.'
    }
  }
  const n = s.rowsRecovered
  return {
    title: `Omi repaired its local database`,
    body:
      `A problem was found at startup and fixed automatically — ${n.toLocaleString()} ` +
      `item${n === 1 ? '' : 's'} recovered. A copy of the old file was saved.`
  }
}

export function DbRecoveryNotice(): React.JSX.Element | null {
  const [status, setStatus] = useState<DbRecoveryStatus | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let alive = true
    void window.omi
      .dbRecoveryStatus()
      .then((s) => {
        if (alive && s.recovered) setStatus(s)
      })
      .catch(() => {
        // A missing/failing status channel must never break the app shell.
      })
    return () => {
      alive = false
    }
  }, [])

  if (!status || dismissed) return null
  const { title, body } = describe(status)

  return (
    <div
      role="status"
      className="glass mx-4 mt-3 flex items-start gap-3 border border-white/15 px-4 py-3"
    >
      <DatabaseBackup className="mt-0.5 h-4 w-4 shrink-0 text-white/85" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white/95">{title}</div>
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
