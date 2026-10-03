/**
 * Where chunks live, and what counts as a legal chunk path.
 *
 * A chunk path is stored in the database and later turned back into a file
 * read, which makes it exactly the shape of input `frameFile.ts` already
 * defends against for JPEGs: a stored string that must not be able to address
 * anything outside the Rewind root. The rules here mirror that file's, and the
 * validation is deliberately duplicated rather than shared, because the two
 * differ in the part that matters (`.jpg` under `<root>` at any depth versus
 * `<day>/<name>.omichunk` at exactly one level) and a single parameterised
 * checker would blur the thing being asserted.
 *
 * macOS validates the same property in
 * `RewindAbandonedVideoChunkJournal.videoURL`: exactly two path components,
 * neither empty nor `.` nor `..`, the right extension, and a final containment
 * check against the storage root. This is that check.
 */

import { resolve, sep } from 'path'

export const CHUNK_EXTENSION = '.omichunk'

/** `<day>/<firstFrameTs>-<lastFrameTs>.omichunk`. */
const RELATIVE_CHUNK_RE = /^\d{4}-\d{2}-\d{2}\/\d{1,15}-\d{1,15}\.omichunk$/

/**
 * The relative path a planned chunk is stored at.
 *
 * Named from the timestamps it spans rather than a counter or a random id, so
 * the filename says what is inside it, two runs over the same frames produce
 * the same name, and a directory listing sorts chronologically.
 */
export function chunkRelativePath(day: string, firstTsMs: number, lastTsMs: number): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error(`invalid chunk day: ${day}`)
  if (!Number.isSafeInteger(firstTsMs) || firstTsMs < 0)
    throw new Error('invalid chunk start timestamp')
  if (!Number.isSafeInteger(lastTsMs) || lastTsMs < firstTsMs)
    throw new Error('invalid chunk end timestamp')
  return `${day}/${firstTsMs}-${lastTsMs}${CHUNK_EXTENSION}`
}

/**
 * Whether a stored string is a chunk path this app could have written.
 *
 * The regex is the load-bearing guard: it pins the whole shape, and by pinning
 * it also rejects `..`, absolute paths, UNC paths, extra path segments and
 * surrounding whitespace. A mutation audit confirmed that both the trim check
 * below and the containment check in `resolveChunkPath` can be deleted without
 * any test noticing, because this pattern already refuses everything they
 * catch.
 *
 * They stay anyway, and the reason is worth stating rather than leaving as
 * apparent redundancy: the shape rule is the kind of thing a later change
 * loosens (a new naming scheme, a nested directory), and the containment check
 * is what would still be standing between a stored string and a file read
 * outside the Rewind root when it does.
 */
export function isChunkRelativePath(relativePath: string): boolean {
  if (typeof relativePath !== 'string') return false
  const trimmed = relativePath.trim()
  if (trimmed !== relativePath) return false
  return RELATIVE_CHUNK_RE.test(relativePath)
}

/**
 * Absolute path for a chunk, or `null` when the stored value is not one this
 * app could have written or escapes the root.
 *
 * Returns `null` rather than throwing because the callers are read paths
 * serving a UI: a frame whose row is corrupt should render as a missing frame,
 * not take down the page.
 *
 * The containment check is defence in depth behind `isChunkRelativePath` — see
 * the note there for why it is kept despite being unobservable today.
 */
export function resolveChunkPath(root: string, relativePath: string): string | null {
  if (!isChunkRelativePath(relativePath)) return null
  const resolvedRoot = resolve(root)
  const candidate = resolve(resolvedRoot, relativePath)
  if (candidate !== resolvedRoot && !candidate.startsWith(resolvedRoot + sep)) return null
  return candidate
}

/** The `<day>` component of a chunk path, for day-scoped retention. */
export function chunkDay(relativePath: string): string | null {
  if (!isChunkRelativePath(relativePath)) return null
  return relativePath.slice(0, relativePath.indexOf('/'))
}
