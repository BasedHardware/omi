import { unlink } from 'fs/promises'
import { retentionCutoff } from './retentionSelection'
import { deleteRewindFramesOlderThan } from '../ipc/db'
import { getRewindSettings } from './captureService'

const PRUNE_INTERVAL_MS = 60 * 60 * 1000 // hourly
const UNLINK_CONCURRENCY = 64

export async function pruneRewindOnce(): Promise<number> {
  const { retentionDays } = getRewindSettings()
  const cutoff = retentionCutoff(Date.now(), retentionDays)
  const removed = deleteRewindFramesOlderThan(cutoff)
  // Delete the JPEGs in bounded-concurrency batches. The first prune after a long
  // gap can return a very large set, and firing every unlink at once would spike
  // main-process memory with that many pending promises.
  for (let i = 0; i < removed.length; i += UNLINK_CONCURRENCY) {
    await Promise.all(
      removed.slice(i, i + UNLINK_CONCURRENCY).map((f) => unlink(f.imagePath).catch(() => undefined))
    )
  }
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
