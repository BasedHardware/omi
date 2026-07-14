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
  // Corruption was CONFIRMED but deliberately not repaired — either the repair
  // budget ran out or a rebuild would have lost rows that still read fine. Say so
  // plainly: nothing was touched, and nothing was thrown away.
  if (s.unrepairable) {
    return {
      title: 'Omi found a problem with its local database',
      body:
        'Omi could not repair it safely, so it left your data exactly as it was. ' +
        'Some items may not load. Nothing has been deleted.'
    }
  }
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

/** Shell for both states, so the two notices look and behave identically. */
function Notice({
  title,
  body,
  onDismiss,
  action
}: {
  title: string
  body: string
  onDismiss: () => void
  action?: { label: string; onClick: () => void }
}): React.JSX.Element {
  return (
    <div
      role="status"
      className="glass mx-4 mt-3 flex items-start gap-3 border border-white/15 px-4 py-3"
    >
      <DatabaseBackup className="mt-0.5 h-4 w-4 shrink-0 text-white/85" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-white/95">{title}</div>
        <div className="mt-0.5 break-words text-xs leading-relaxed text-white/65">{body}</div>
        {action && (
          <button
            onClick={action.onClick}
            className="btn-primary mt-2 px-3 py-1 text-xs"
            type="button"
          >
            {action.label}
          </button>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="-mr-1 -mt-1 rounded-md p-1 text-white/45 hover:bg-white/10 hover:text-white"
        aria-label="Dismiss"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export function DbRecoveryNotice(): React.JSX.Element | null {
  const [status, setStatus] = useState<DbRecoveryStatus | null>(null)
  const [needsRestart, setNeedsRestart] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let alive = true
    void window.omi
      .dbRecoveryStatus()
      .then((s) => {
        if (alive && (s.recovered || s.unrepairable)) setStatus(s)
      })
      .catch(() => {
        // A missing/failing status channel must never break the app shell.
      })
    // A live query hit corruption THIS session. The repair only runs at startup
    // (the KG worker and the read-only handle are live now), so ask for a restart.
    const unsubscribe = window.omi.onDbCorruptionDetected(() => {
      if (alive) setNeedsRestart(true)
    })
    return () => {
      // Both must be torn down: the flag stops the in-flight status promise from
      // setting state after unmount, the unsubscribe drops the IPC listener.
      alive = false
      unsubscribe()
    }
  }, [])

  // The restart prompt wins: it is actionable, and it is about right now.
  if (needsRestart && !dismissed) {
    return (
      <Notice
        title="Omi hit a problem with its local database"
        // Honest: nothing is lost yet, and the restart is a repair, not a wipe.
        body="Restart Omi and it will repair the database automatically. Your data is still on disk."
        onDismiss={() => setDismissed(true)}
        action={{ label: 'Restart Omi', onClick: () => window.omi.relaunchApp() }}
      />
    )
  }

  if (!status || dismissed) return null
  const { title, body } = describe(status)
  return <Notice title={title} body={body} onDismiss={() => setDismissed(true)} />
}
