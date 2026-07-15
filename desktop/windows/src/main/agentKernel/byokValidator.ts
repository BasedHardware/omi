// Per-provider health-check pings for BYOK keys, ported from the macOS
// `BYOKValidator` (desktop/macos/Desktop/Sources/BYOKValidator.swift).
//
// We never flip the backend onto the BYOK free plan with a dead key: enrollment
// live-validates all four keys first. Each ping hits the provider's cheapest
// auth-gated endpoint; any 2xx means the key at least authenticates (billing
// problems surface later as a normal inference error — not a key-shape problem
// we could have caught up front). A 401/403 is a definitive rejection.
//
// Runs in the MAIN process: the renderer's CSP/CORS blocks these provider
// domains, and main has the unrestricted `fetch` (undici) needed to reach them.

import {
  BYOK_PROVIDERS,
  type ByokKeys,
  type ByokKeyValidation,
  type ByokProvider,
  type ByokValidationResults
} from '../../shared/byok'

export type { ByokKeyValidation, ByokValidationResults } from '../../shared/byok'

/** Minimal fetch shape we depend on — injectable so tests need no network. */
export type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; signal: AbortSignal }
) => Promise<{ status: number }>

const TIMEOUT_MS = 8_000

/** The provider request (endpoint + auth header) for a trimmed key. */
function providerRequest(
  provider: ByokProvider,
  key: string
): { url: string; headers: Record<string, string> } {
  switch (provider) {
    case 'openai':
      return { url: 'https://api.openai.com/v1/models', headers: { Authorization: `Bearer ${key}` } }
    case 'anthropic':
      return {
        url: 'https://api.anthropic.com/v1/models?limit=1',
        headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01' }
      }
    case 'gemini':
      return {
        url: `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
        headers: {}
      }
    case 'deepgram':
      return {
        url: 'https://api.deepgram.com/v1/projects',
        headers: { Authorization: `Token ${key}` }
      }
  }
}

/**
 * Ping one provider and classify the result. Empty keys fail without a request.
 * 2xx → ok; 401/403 → definitive rejection; other status → transient HTTP
 * failure; abort → timeout; anything thrown → network. Never logs or returns
 * the key.
 */
export async function validateProviderKey(
  provider: ByokProvider,
  key: string,
  fetchImpl: FetchLike = globalThis.fetch as unknown as FetchLike
): Promise<ByokKeyValidation> {
  const trimmed = key.trim()
  if (!trimmed) return { ok: false, kind: 'empty', detail: 'No key entered' }

  const { url, headers } = providerRequest(provider, trimmed)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const res = await fetchImpl(url, { method: 'GET', headers, signal: controller.signal })
    if (res.status >= 200 && res.status < 300) return { ok: true }
    if (res.status === 401 || res.status === 403) {
      return { ok: false, kind: 'rejected', detail: `Rejected by provider (HTTP ${res.status})` }
    }
    return { ok: false, kind: 'http', detail: `Provider error (HTTP ${res.status})` }
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return { ok: false, kind: 'timeout', detail: 'Timed out reaching provider' }
    }
    return { ok: false, kind: 'network', detail: "Couldn't reach provider" }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Validate every provider in `keys` in parallel. Only the four canonical
 * providers are checked; missing entries are validated as empty (fail), so the
 * caller can treat a non-`ok` result uniformly as "not all four authenticate".
 */
export async function validateAllByokKeys(
  keys: ByokKeys,
  fetchImpl: FetchLike = globalThis.fetch as unknown as FetchLike
): Promise<ByokValidationResults> {
  const entries = await Promise.all(
    BYOK_PROVIDERS.map(
      async (provider): Promise<[ByokProvider, ByokKeyValidation]> => [
        provider,
        await validateProviderKey(provider, keys[provider] ?? '', fetchImpl)
      ]
    )
  )
  return Object.fromEntries(entries) as ByokValidationResults
}
