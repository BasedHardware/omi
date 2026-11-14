import { retentionCutoff } from './retentionSelection'
import { deleteParkedRewindFramesOlderThan, deleteRewindFramesOlderThan } from '../ipc/db'
import { getRewindSettings } from './captureService'
import { rewindRoot } from './paths'
import { removeRewindFrame } from './frameFile'

const PRUNE_INTERVAL_MS = 60 * 60 * 1000 // hourly

const unlinkPruned = (rows: Array<{ imagePath: string }>): Promise<unknown>[] =>
  rows.map((f) =>
    removeRewindFrame(rewindRoot(), f.imagePath).catch((error: NodeJS.ErrnoException) => {
      // ENOENT is idempotent (frame already gone). Other failures need a log
      // so retention cannot silently leave disk growth undiagnosed.
      if (error?.code !== 'ENOENT') {
        console.warn('[rewind] failed to delete pruned frame:', f.imagePath, error)
      }
    })
  )

export async function pruneRewindOnce(): Promise<number> {
  const { retentionDays } = getRewindSettings()
  const now = Date.now()
  const cutoff = retentionCutoff(now, retentionDays)
  const removed = deleteRewindFramesOlderThan(cutoff)
  // Parked rows share the same cutoff: a parked owner who never signs back in
  // must age out too, or their rows (and, via the sweep's keep-set, their
  // JPEGs) would accumulate forever.
  const parkedRemoved = deleteParkedRewindFramesOlderThan(cutoff)
  await Promise.all([...unlinkPruned(removed), ...unlinkPruned(parkedRemoved)])
  return removed.length + parkedRemoved.length
}

export function startRewindRetention(): void {
  // Prune once on launch so a restart enforces retention promptly (not only
  // after the first hourly tick), and surface failures instead of dropping them.
  void pruneRewindOnce().catch((e) => console.warn('[rewind] initial prune failed:', e))
  setInterval(() => {
    void pruneRewindOnce().catch((e) => console.warn('[rewind] prune failed:', e))
  }, PRUNE_INTERVAL_MS)
}
