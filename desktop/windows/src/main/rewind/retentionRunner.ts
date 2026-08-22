import { retentionCutoff } from './retentionSelection'
import { deleteRewindFramesOlderThan, referencedChunkPaths } from '../ipc/db'
import { getRewindSettings } from './captureService'
import { rewindRoot } from './paths'
import { removeRewindFrame } from './frameFile'
import { listChunkFiles, removeChunkFile, selectUnreferencedChunks } from './chunks/chunkFiles'

const PRUNE_INTERVAL_MS = 60 * 60 * 1000 // hourly

export async function pruneRewindOnce(): Promise<number> {
  const { retentionDays } = getRewindSettings()
  const cutoff = retentionCutoff(Date.now(), retentionDays)
  const removed = deleteRewindFramesOlderThan(cutoff)
  await Promise.all(
    removed
      // A compacted frame has no JPEG of its own — its pixels live in a chunk,
      // and its `image_path` was set to '' when it was claimed. Passing that to
      // removeRewindFrame would raise "invalid frame path" for every such frame
      // and log a warning per row. The chunk file itself is collected below,
      // once the last frame pointing into it is gone.
      .filter((f) => f.imagePath !== '')
      .map((f) =>
        removeRewindFrame(rewindRoot(), f.imagePath).catch((error: NodeJS.ErrnoException) => {
          // ENOENT is idempotent (frame already gone). Other failures need a log
          // so retention cannot silently leave disk growth undiagnosed.
          if (error?.code !== 'ENOENT') {
            console.warn('[rewind] failed to delete pruned frame:', f.imagePath, error)
          }
        })
      )
  )
  await collectDeadChunks()
  return removed.length
}

/**
 * Delete chunk files nothing points at any more.
 *
 * This is the chunk half of retention. Frames are deleted by age above; a chunk
 * becomes garbage the moment its last frame goes, and there is no foreign key
 * to notice. It also collects a chunk written by a compaction that crashed
 * before claiming anything, which is why it works from "what is on disk minus
 * what is referenced" rather than from a list of chunks to delete.
 */
export async function collectDeadChunks(nowMs: number = Date.now()): Promise<number> {
  const root = rewindRoot()
  let onDisk: { relativePath: string; modifiedMs: number }[]
  try {
    onDisk = await listChunkFiles(root)
  } catch (e) {
    console.warn('[rewind] could not list chunk files:', e)
    return 0
  }
  if (onDisk.length === 0) return 0

  const dead = selectUnreferencedChunks(onDisk, referencedChunkPaths(), nowMs)
  let removed = 0
  for (const relativePath of dead) {
    try {
      await removeChunkFile(root, relativePath)
      removed++
    } catch (error) {
      const code = (error as NodeJS.ErrnoException)?.code
      if (code !== 'ENOENT') console.warn('[rewind] failed to delete chunk:', relativePath, error)
    }
  }
  if (removed > 0) console.log(`[rewind] collected ${removed} unreferenced chunk file(s)`)
  return removed
}

export function startRewindRetention(): void {
  // Prune once on launch so a restart enforces retention promptly (not only
  // after the first hourly tick), and surface failures instead of dropping them.
  void pruneRewindOnce().catch((e) => console.warn('[rewind] initial prune failed:', e))
  setInterval(() => {
    void pruneRewindOnce().catch((e) => console.warn('[rewind] prune failed:', e))
  }, PRUNE_INTERVAL_MS)
}
