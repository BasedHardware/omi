// BYOK (Bring Your Own Keys) header + fingerprint helpers.
//
// Mirrors the backend contract in `backend/utils/byok.py` (BYOK_HEADERS,
// SHA-256 fingerprints) and the Rust `Backend-Rust/src/byok.rs`. The desktop
// client sends user-provided provider keys as per-request headers; the backend
// reads them case-insensitively (`x-byok-{provider}`) but clients send the
// canonical casing below. The backend enforces ALL-OR-NOTHING enrollment via
// `has_all_byok_keys()` — a partial set is not a valid BYOK-active state.
//
// Pure module: the only dependency is `node:crypto` (used by the fingerprint
// helper, which runs in the main process only). No Electron / no I/O.

import { createHash } from 'node:crypto'

/** A provider whose API key a user can bring themselves. */
export type ByokProvider = 'openai' | 'anthropic' | 'gemini' | 'deepgram'

/** The four BYOK providers, in the backend's canonical order. */
export const BYOK_PROVIDERS: readonly ByokProvider[] = ['openai', 'anthropic', 'gemini', 'deepgram']

/** Canonical header casing clients send (backend matches case-insensitively). */
export const BYOK_HEADER_NAMES: Record<ByokProvider, string> = {
  openai: 'X-BYOK-OpenAI',
  anthropic: 'X-BYOK-Anthropic',
  gemini: 'X-BYOK-Gemini',
  deepgram: 'X-BYOK-Deepgram'
}

/** A (possibly partial) map of provider → raw provider key. */
export type ByokKeys = Partial<Record<ByokProvider, string>>

/**
 * Return a NEW headers object with `X-BYOK-*` attached for every provider that
 * has a non-empty trimmed key. Keys are sent raw (trimmed, NO `Bearer` prefix)
 * exactly as the backend expects. Never mutates the input `headers` or `keys`.
 */
export function withByokHeaders(
  headers: Record<string, string>,
  keys: ByokKeys
): Record<string, string> {
  const out: Record<string, string> = { ...headers }
  for (const provider of BYOK_PROVIDERS) {
    const value = keys[provider]?.trim()
    if (value) {
      out[BYOK_HEADER_NAMES[provider]] = value
    }
  }
  return out
}

/**
 * True only when ALL four providers have a non-empty trimmed key — matches the
 * backend's all-or-nothing gate (`has_all_byok_keys()`). A partial set is not
 * BYOK-active.
 */
export function isByokActive(keys: ByokKeys): boolean {
  return BYOK_PROVIDERS.every((provider) => Boolean(keys[provider]?.trim()))
}

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
