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

/** An offer of something the user can DO about the state of their database. A list,
 *  not a single slot: the Rewind index rebuild (macOS has that button in exactly
 *  this banner) hangs off the same row without reshaping the component. */
type NoticeAction = { label: string; onClick: () => void; disabled?: boolean }

/** Shell for every state, so the notices look and behave identically. */
function Notice({
  title,
  body,
  onDismiss,
  actions = []
}: {
  title: string
  body: string
  onDismiss: () => void
  actions?: NoticeAction[]
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
        {actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {actions.map((a) => (
              <button
                key={a.label}
                onClick={a.onClick}
                disabled={a.disabled}
                className="btn-primary px-3 py-1 text-xs disabled:cursor-default disabled:opacity-60"
                type="button"
              >
                {a.label}
              </button>
            ))}
          </div>
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

// Progress of the optional "Rebuild Rewind Index" action. When the local DB was
// reset/recovered, rewind_frames may have been wiped while the screenshot JPEGs
// survived on disk — this lets the user re-create those rows (indexed=0 so the OCR
// backfill re-indexes them). Idempotent + insert-only on the main side.
type RebuildState = { phase: 'idle' } | { phase: 'running' } | { phase: 'done'; count: number }

export function DbRecoveryNotice(): React.JSX.Element | null {
  const [status, setStatus] = useState<DbRecoveryStatus | null>(null)
  const [needsRestart, setNeedsRestart] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [rebuild, setRebuild] = useState<RebuildState>({ phase: 'idle' })

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
        actions={[{ label: 'Restart Omi', onClick: () => window.omi.relaunchApp() }]}
      />
    )
  }

  if (!status || dismissed) return null
  const { title, body } = describe(status)

  // Offer the Rewind rebuild only when rows may actually have been lost — i.e. the
  // DB was reset or repaired. On the 'unrepairable' path nothing was touched, so
  // there's nothing to rebuild. The rebuild itself is safe (insert-only, idempotent)
  // regardless, but showing it there would just be noise.
  const rowsMayBeLost = status.reset || status.recovered
  const actions: NoticeAction[] = []
  if (rowsMayBeLost && !status.unrepairable) {
    const runRebuild = (): void => {
      setRebuild({ phase: 'running' })
      void window.omi
        .rewindRebuildIndex()
        .then((count) => setRebuild({ phase: 'done', count }))
        // A failure just returns the button to idle so the user can retry; the
        // rebuild never partially destroys anything, so there's nothing to warn about.
        .catch(() => setRebuild({ phase: 'idle' }))
    }
    const label =
      rebuild.phase === 'running'
        ? 'Rebuilding Rewind index…'
        : rebuild.phase === 'done'
          ? rebuild.count > 0
            ? `Rebuilt Rewind index (${rebuild.count.toLocaleString()} recovered)`
            : 'Rewind index up to date'
          : 'Rebuild Rewind Index'
    actions.push({
      label,
      onClick: runRebuild,
      disabled: rebuild.phase !== 'idle'
    })
  }

  return <Notice title={title} body={body} onDismiss={() => setDismissed(true)} actions={actions} />
}
