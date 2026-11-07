/**
 * Chunk files on disk.
 *
 * Main owns every read and write, exactly as it already does for JPEGs
 * (`frameFile.ts`). The renderer that runs the codec never touches the
 * filesystem; it is handed bytes and hands bytes back.
 *
 * The write is atomic because the compactor's safety argument depends on it:
 * "the chunk is durable before any row points at it" is only true if a torn
 * write cannot be mistaken for a finished one. Writing to a temporary name and
 * renaming means a reader either sees the whole chunk or no chunk.
 */

import { mkdir, readFile, rename, rm, unlink, writeFile, readdir, stat } from 'fs/promises'
import { dirname, join } from 'path'
import { chunkDay, isChunkRelativePath, resolveChunkPath } from './chunkPaths'

/**
 * A chunk file younger than this is never collected as unreferenced.
 *
 * The window between writing a chunk and claiming its first frame is real, and
 * during it the file is legitimately unreferenced. Without this grace the sweep
 * could delete a chunk out from under the compactor that just wrote it. The
 * same reasoning (and roughly the same value) as `ORPHAN_GRACE_MS` in
 * `orphanSelection.ts`, which exists for the mirror-image race on JPEGs.
 */
export const CHUNK_SWEEP_GRACE_MS = 10 * 60_000

const DAY_DIR_RE = /^\d{4}-\d{2}-\d{2}$/

export async function writeChunkFile(
  root: string,
  relativePath: string,
  bytes: Uint8Array
): Promise<void> {
  const absolute = resolveChunkPath(root, relativePath)
  if (!absolute) throw new Error(`refusing to write chunk at ${relativePath}`)
  await mkdir(dirname(absolute), { recursive: true })
  // `.tmp` is deliberately not a chunk path, so a leftover temp file can never
  // be mistaken for a chunk by the reader or the sweep.
  //
  // The atomicity this buys cannot be observed from a unit test — it only shows
  // up when the process dies between the write and the rename — so no test here
  // fails if the rename is removed. It is load-bearing regardless: the
  // compactor's safety argument is "the chunk is durable before any row points
  // at it", and a torn write that a reader could mistake for a finished chunk
  // is precisely the case that breaks it.
  const temporary = `${absolute}.tmp`
  await writeFile(temporary, bytes)
  await rename(temporary, absolute)
}

export async function readChunkFile(root: string, relativePath: string): Promise<Buffer> {
  const absolute = resolveChunkPath(root, relativePath)
  if (!absolute) throw new Error(`refusing to read chunk at ${relativePath}`)
  return readFile(absolute)
}

export async function removeChunkFile(root: string, relativePath: string): Promise<void> {
  const absolute = resolveChunkPath(root, relativePath)
  if (!absolute) throw new Error(`refusing to delete chunk at ${relativePath}`)
  await rm(absolute, { force: true })
}

/** Every chunk file under the root, as relative paths, with its modified time. */
export async function listChunkFiles(
  root: string
): Promise<{ relativePath: string; modifiedMs: number }[]> {
  let days: string[]
  try {
    days = await readdir(root)
  } catch {
    return []
  }
  const found: { relativePath: string; modifiedMs: number }[] = []
  for (const day of days) {
    // Skipping non-day directories is an optimisation, not a guard: the
    // `isChunkRelativePath` check below rejects anything outside a day
    // directory anyway. It is kept because the alternative is descending into
    // every unrelated directory under the Rewind root and building a candidate
    // path per file. A mutation audit confirmed removing it changes no output.
    if (!DAY_DIR_RE.test(day)) continue
    let entries: string[]
    try {
      entries = await readdir(join(root, day))
    } catch {
      continue // vanished between listing and read
    }
    for (const entry of entries) {
      // One authority for what counts as a chunk. There was a cheap
      // `entry.endsWith(CHUNK_EXTENSION)` pre-filter here as well; the audit
      // showed it could be deleted without any test noticing, because this
      // check subsumes it. A guard that cannot be shown to matter is a guard
      // that will drift, so there is now only one.
      const relativePath = `${day}/${entry}`
      if (!isChunkRelativePath(relativePath)) continue
      try {
        const info = await stat(join(root, day, entry))
        found.push({ relativePath, modifiedMs: info.mtimeMs })
      } catch {
        continue
      }
    }
  }
  return found
}

/**
 * Chunk files no frame references any more.
 *
 * Pure so the grace-period rule can be tested without a filesystem. Retention
 * deletes rows by age; a chunk becomes garbage when its last row goes, and this
 * is what notices. It also catches a chunk the database never heard of, which
 * is the crash-after-write case.
 */
export function selectUnreferencedChunks(
  onDisk: { relativePath: string; modifiedMs: number }[],
  referenced: string[],
  nowMs: number,
  graceMs = CHUNK_SWEEP_GRACE_MS
): string[] {
  const live = new Set(referenced)
  return onDisk
    .filter((f) => !live.has(f.relativePath))
    .filter((f) => nowMs - f.modifiedMs >= graceMs)
    .map((f) => f.relativePath)
}

/** Day directories a set of chunk paths touches, for logging and day-scoped work. */
export function daysTouched(relativePaths: string[]): string[] {
  const days = new Set<string>()
  for (const path of relativePaths) {
    const day = chunkDay(path)
    if (day) days.add(day)
  }
  return [...days].sort()
}

/** Remove a stale `.tmp` left by a write that died mid-flight. */
export async function removeTemporaryChunk(root: string, relativePath: string): Promise<void> {
  const absolute = resolveChunkPath(root, relativePath)
  if (!absolute) return
  await unlink(`${absolute}.tmp`).catch(() => undefined)
}
