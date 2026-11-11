// Float32 (L2-normalized) ⇄ SQLite BLOB conversion for task embedding vectors,
// stored as a row BLOB on action_items / staged_tasks.
//
// Kept in a better-sqlite3-free module (like dbWipe.ts) so the byte-level
// conversion — the one bit of non-SQL logic in the Track 3 embedding store — is
// unit-testable under plain-node vitest (better-sqlite3 is built for Electron's
// ABI and won't load there). db.ts imports these; the DB just stores the bytes.
//
// Little-endian is assumed on both ends, which holds on every platform we ship
// (x86-64, arm64).

/** Zero-copy view of a Float32Array's bytes as a Buffer, for binding to a BLOB
 *  column. better-sqlite3 copies the bytes at bind time, so the view is safe. */
export function vectorToBuffer(v: Float32Array): Buffer {
  return Buffer.from(v.buffer, v.byteOffset, v.byteLength)
}

/** Rebuild a Float32Array from BLOB bytes (Buffer from better-sqlite3, Uint8Array
 *  from node:sqlite). Copies into a fresh, 4-byte-aligned ArrayBuffer because a
 *  pooled Buffer's byteOffset is not guaranteed to be a multiple of 4, which a
 *  Float32Array view requires. */
export function bufferToVector(b: Buffer | Uint8Array): Float32Array {
  const out = new Float32Array(Math.floor(b.byteLength / 4))
  new Uint8Array(out.buffer).set(b.subarray(0, out.byteLength))
  return out
}
