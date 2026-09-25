// Atomic file write: write to a temp file in the SAME directory as the REAL
// target, fsync it, then rename over the target. rename() is atomic on the same
// filesystem (libuv maps it to MoveFileEx with REPLACE_EXISTING on Windows), so
// a crash / power loss mid-write can never leave the target truncated or
// half-written — readers see either the old file or the new one, never a
// corrupt one. The temp lives beside the real target (a cross-device rename
// from %TEMP% would fail), gets a unique name, and is cleaned up if the write
// or rename throws.
//
// `path` may be a symlink (user-configured config redirects): realpathSync
// resolves it so the rename swaps the REAL file and the link survives. A broken
// symlink is refused outright — renaming over it would silently unlink it.
//
// Used for the user's LIVE config files (~/.claude.json can be 500KB+ with the
// external Claude CLI reading it) and the encrypted key store. Pair it with a
// backup-before-write where the caller wants a recovery net too.

import {
  writeFileSync,
  renameSync,
  rmSync,
  realpathSync,
  lstatSync,
  openSync,
  fsyncSync,
  closeSync
} from 'fs'
import { dirname, join, basename } from 'path'

// Process-unique, monotonic suffix so concurrent/rapid writes never collide on
// the temp name (no Math.random / Date — deterministic for tests).
let seq = 0

export function atomicWriteFileSync(path: string, data: string, mode?: number): void {
  let target = path
  try {
    target = realpathSync(path)
  } catch (e) {
    // Absent file → create it in place. A symlink whose target is missing is a
    // BROKEN link: refuse rather than unlink it via a rename over the link.
    let isLink = false
    try {
      isLink = lstatSync(path).isSymbolicLink()
    } catch {
      /* not present at all */
    }
    if (isLink) throw e
  }
  const tmp = join(dirname(target), `.${basename(target)}.omi-tmp-${process.pid}-${seq++}`)
  try {
    // `mode` applies only when the temp is created; on Windows POSIX permission
    // bits are ignored by libuv, so callers get a graceful no-op there.
    const fd = openSync(tmp, 'w', mode)
    try {
      writeFileSync(fd, data, 'utf8')
      // Durably on disk before the rename, so a crash can't rename in a temp
      // whose contents were never flushed.
      fsyncSync(fd)
    } finally {
      closeSync(fd)
    }
    renameSync(tmp, target)
  } catch (e) {
    try {
      rmSync(tmp, { force: true })
    } catch {
      /* temp already gone / unremovable — best-effort cleanup */
    }
    throw e
  }
}
