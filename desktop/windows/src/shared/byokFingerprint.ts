// BYOK enrollment fingerprint — SHA-256 of the raw provider key.
//
// Split out from `byok.ts` because it depends on `node:crypto` and therefore
// runs in the MAIN process only. Keeping it here lets `byok.ts` stay a pure,
// browser-safe module (header/active/env helpers) that the renderer can import
// for the axios/fetch injection lanes without pulling `node:crypto` into the
// web bundle.

import { createHash } from 'node:crypto'

/**
 * SHA-256 hex (lowercase) of the raw key — the enrollment fingerprint the
 * backend stores and validates against (regex `^[a-f0-9]{64}$`). Used for
 * enrollment/verification, never as a header value. The key is hashed
 * trimmed to match the wire value `withByokHeaders` actually sends (the
 * backend re-hashes the trimmed header value to validate enrollment).
 */
export function byokFingerprint(key: string): string {
  return createHash('sha256').update(key.trim(), 'utf8').digest('hex')
}
