import { unlink } from 'fs/promises'
import { retentionCutoff } from './retentionSelection'
import { deleteRewindFramesOlderThan } from '../ipc/db'
import { getRewindSettings } from './captureService'

const PRUNE_INTERVAL_MS = 60 * 60 * 1000 // hourly

export async function pruneRewindOnce(): Promise<number> {
  const { retentionDays } = getRewindSettings()
  const cutoff = retentionCutoff(Date.now(), retentionDays)
  const removed = deleteRewindFramesOlderThan(cutoff)
  await Promise.all(
    removed.map((f) => unlink(f.imagePath).catch(() => undefined)) // file may already be gone
  )
  return removed.length
}

export function startRewindRetention(): void {
  setInterval(() => void pruneRewindOnce(), PRUNE_INTERVAL_MS)
}
