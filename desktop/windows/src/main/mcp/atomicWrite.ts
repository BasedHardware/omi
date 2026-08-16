// Atomic file write: write to a temp file in the SAME directory, then rename it
// over the target. rename() is atomic on the same filesystem (libuv maps it to
// MoveFileEx with REPLACE_EXISTING on Windows), so a crash / power loss mid-write
// can never leave the target truncated or half-written — readers see either the
// old file or the new one, never a corrupt one. The temp lives in the target's
// dir (a cross-device rename from %TEMP% would fail), gets a unique name, and is
// cleaned up if the write or rename throws.
//
// Used for the user's LIVE config files (~/.claude.json can be 500KB+ with the
// external Claude CLI reading it) and the encrypted key store. Pair it with a
// backup-before-write where the caller wants a recovery net too.

import { writeFileSync, renameSync, rmSync } from 'fs'
import { dirname, join, basename } from 'path'

// Process-unique, monotonic suffix so concurrent/rapid writes never collide on
// the temp name (no Math.random / Date — deterministic for tests).
let seq = 0

export function atomicWriteFileSync(path: string, data: string): void {
  const tmp = join(dirname(path), `.${basename(path)}.omi-tmp-${process.pid}-${seq++}`)
  try {
    writeFileSync(tmp, data, 'utf8')
    renameSync(tmp, path)
  } catch (e) {
    try {
      rmSync(tmp, { force: true })
    } catch {
      /* temp already gone / unremovable — best-effort cleanup */
    }
    throw e
  }
}
