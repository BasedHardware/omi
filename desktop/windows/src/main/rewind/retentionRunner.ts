import { retentionCutoff } from './retentionSelection'
import { deleteRewindFramesOlderThan } from '../ipc/db'
import { getRewindSettings } from './captureService'
import { rewindRoot } from './paths'
import { removeRewindFrame } from './frameFile'

const PRUNE_INTERVAL_MS = 60 * 60 * 1000 // hourly

export async function pruneRewindOnce(): Promise<number> {
  const { retentionDays } = getRewindSettings()
  const cutoff = retentionCutoff(Date.now(), retentionDays)
  const removed = deleteRewindFramesOlderThan(cutoff)
  await Promise.all(
    removed.map((f) => removeRewindFrame(rewindRoot(), f.imagePath).catch(() => undefined)) // file may already be gone
  )
  return removed.length
}

export function startRewindRetention(): void {
  // Prune once on launch so a restart enforces retention promptly (not only
  // after the first hourly tick), and surface failures instead of dropping them.
  void pruneRewindOnce().catch((e) => console.warn('[rewind] initial prune failed:', e))
  setInterval(() => {
    void pruneRewindOnce().catch((e) => console.warn('[rewind] prune failed:', e))
  }, PRUNE_INTERVAL_MS)
}
