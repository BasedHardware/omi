// Renderer-side in-memory BYOK key + capability cache for the REST/fetch lanes.
//
// The keys live encrypted in the main process (ByokKeyStore). The axios
// interceptor (apiClient) and the raw `/v2/messages` fetch (useChat) run in the
// renderer and need the raw keys to attach X-BYOK-* headers, but they can't
// `await` an IPC round-trip per request. So we mirror the key set into memory
// once at startup and refresh it whenever main broadcasts `byok:changed`.
//
// Alongside the raw keys we mirror the VALIDATED capability set: providers whose
// stored key still matches the fingerprint the backend accepted at the last
// successful enrollment. Quota suppression must key off this, not presence — a
// configured-but-rejected Deepgram key stays stored locally while the backend
// meters managed credits.
//
// This cache is never persisted and never logged.

import {
  BYOK_LLM_PROVIDERS,
  isByokActive,
  withByokHeaders,
  type ByokKeys,
  type ByokProvider
} from '../../../shared/byok'

let cached: ByokKeys = {}
let cachedValidated: ByokProvider[] = []

/** Reload the cache from the main-process store. */
export async function refreshByokKeys(): Promise<void> {
  try {
    const [keys, validated] = await Promise.all([
      window.omi?.byokGetAll?.() ?? {},
      window.omi?.byokValidatedProviders?.() ?? []
    ])
    cached = keys
    cachedValidated = validated
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

/**
 * True when a validated (enrolled, unrotated) Deepgram key backs managed-STT
 * quota suppression. Deliberately NOT raw key presence: a configured-but-
 * rejected key must keep the exhaustion popup actionable.
 */
export function hasTranscriptionByokCached(): boolean {
  return cachedValidated.includes('deepgram')
}

/** True when any LLM provider holds validated enrollment evidence. */
export function llmByokValidatedCached(): boolean {
  return cachedValidated.some((p) => (BYOK_LLM_PROVIDERS as readonly string[]).includes(p))
}

/**
 * Synchronously empty the cache. Called from the sign-out teardown so a second
 * account on this install can't have the prior user's keys attached to its
 * requests before the async `byok:changed` reload lands.
 */
export function resetByokKeys(): void {
  cached = {}
  cachedValidated = []
}

// Self-initialize in the renderer: load once and keep in sync. Guarded on
// `window` so importing this module in a non-renderer context (tests) is inert.
if (typeof window !== 'undefined') {
  void refreshByokKeys()
  window.omi?.onByokChanged?.(() => {
    void refreshByokKeys()
  })
}
