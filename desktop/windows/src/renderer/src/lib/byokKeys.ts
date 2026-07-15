// Renderer-side in-memory BYOK key cache for the REST/fetch header lanes.
//
// The keys live encrypted in the main process (ByokKeyStore). The axios
// interceptor (apiClient) and the raw `/v2/messages` fetch (useChat) run in the
// renderer and need the raw keys to attach X-BYOK-* headers, but they can't
// `await` an IPC round-trip per request. So we mirror the key set into memory
// once at startup and refresh it whenever main broadcasts `byok:changed`.
//
// All-or-none: headers are attached only when all four providers have a key
// (matching the backend, which 403s a partial set from an enrolled user).
// This cache is never persisted and never logged.

import { isByokActive, withByokHeaders, type ByokKeys } from '../../../shared/byok'

let cached: ByokKeys = {}

/** Reload the cache from the main-process store. */
export async function refreshByokKeys(): Promise<void> {
  try {
    cached = (await window.omi?.byokGetAll?.()) ?? {}
  } catch {
    // A failed load leaves the previous cache in place; a later `byok:changed`
    // (or the next app start) reloads. Never throw into the request path.
  }
}

/**
 * Attach X-BYOK-* headers to `headers` when BYOK is active (all four keys
 * present), else return `headers` unchanged. Never mutates the input.
 */
export function withByokHeadersIfActive<T extends Record<string, string>>(headers: T): T {
  if (!isByokActive(cached)) return headers
  return withByokHeaders(headers, cached) as T
}

/** True when the cached key set is complete (all four providers). */
export function isByokActiveCached(): boolean {
  return isByokActive(cached)
}

// Self-initialize in the renderer: load once and keep in sync. Guarded on
// `window` so importing this module in a non-renderer context (tests) is inert.
if (typeof window !== 'undefined') {
  void refreshByokKeys()
  window.omi?.onByokChanged?.(() => {
    void refreshByokKeys()
  })
}
