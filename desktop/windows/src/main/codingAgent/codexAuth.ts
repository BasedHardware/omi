// Codex API-key lane — the easy, OAuth-free way to auth Codex from inside Omi.
// Codex's ACP bridge authenticates either via the user's ChatGPT login
// (`codex login`, machine-level) OR via an OpenAI API key. This module owns the
// key path: paste a key → we validate it against OpenAI → store it encrypted →
// inject it as OPENAI_API_KEY into the Codex subprocess at spawn.
//
// STORAGE: reuses the existing encrypted key store (`ByokKeyStore`, safeStorage /
// DPAPI at rest) and its `openai` slot — it is literally the user's OpenAI key,
// so there is one place for it, not two. Consequences of reusing that slot:
//  - A lone Codex key never activates pi-mono BYOK: that path is all-or-nothing
//    (needs all four providers), so a single `openai` key has no BYOK effect.
//  - If the user IS fully BYOK-enrolled, Codex reuses that same OpenAI key.
// The store inherits ByokKeyStore's security posture verbatim (it is the same
// file); like the other BYOK keys it currently persists across sign-out.
//
// The stored key NEVER crosses to the renderer — status is boolean-only, and the
// key is never logged.

import { ByokKeyStore } from '../agentKernel/byokStore'
import type { CodexKeyResult, CodexKeyStatus } from '../../shared/types'

/** The subset of ByokKeyStore this module needs (so tests can inject a fake
 *  without Electron safeStorage). */
type CodexKeyBackingStore = Pick<ByokKeyStore, 'getKey' | 'setKey' | 'clearKey'>

// Lazily constructed so this module stays import-pure (ByokKeyStore's default
// constructor calls app.getPath, which isn't ready at import time).
let store: CodexKeyBackingStore | null = null

function getStore(): CodexKeyBackingStore {
  if (!store) store = new ByokKeyStore()
  return store
}

/** The stored Codex OpenAI key, or null. Read by the adapter registry at spawn. */
export function getCodexApiKey(): string | null {
  try {
    return getStore().getKey('openai')
  } catch {
    return null
  }
}

/** Boolean-only status for the renderer (never returns the key itself). */
export function codexApiKeyStatus(): CodexKeyStatus {
  return { hasKey: getCodexApiKey() != null }
}

/** Minimal fetch shape so validation is unit-testable without a network. */
export type FetchLike = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; signal?: AbortSignal }
) => Promise<{ status: number }>

const VALIDATE_TIMEOUT_MS = 8000

/**
 * Validate a key against OpenAI by listing models with it. 200 = good,
 * 401 = rejected, anything else = unexpected, thrown = unreachable. Only the
 * user's own key is sent, as a Bearer header, to the canonical OpenAI endpoint.
 */
export async function validateOpenAiKey(
  key: string,
  fetchImpl: FetchLike = fetch as unknown as FetchLike
): Promise<{ ok: boolean; status?: number; unreachable?: boolean; error?: string }> {
  const trimmed = key.trim()
  if (!trimmed) return { ok: false, error: 'Enter a key first.' }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), VALIDATE_TIMEOUT_MS)
  try {
    const res = await fetchImpl('https://api.openai.com/v1/models', {
      method: 'GET',
      headers: { Authorization: `Bearer ${trimmed}` },
      signal: controller.signal
    })
    if (res.status === 200) return { ok: true, status: 200 }
    if (res.status === 401) {
      return { ok: false, status: 401, error: 'OpenAI rejected that key. Check it and try again.' }
    }
    return { ok: false, status: res.status, error: `OpenAI returned status ${res.status}.` }
  } catch {
    return { ok: false, unreachable: true, error: 'Could not reach OpenAI to verify the key.' }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Save (or clear) the Codex OpenAI key. A blank key clears it. Otherwise we
 * validate first: a definitive 401 is NOT stored (a known-bad key would only
 * make every Codex run fail); a 200 stores clean; an unreachable network stores
 * anyway (benefit of the doubt) with a soft warning so the user can proceed
 * offline.
 */
export async function saveCodexApiKey(
  key: string,
  validate: typeof validateOpenAiKey = validateOpenAiKey
): Promise<CodexKeyResult> {
  const trimmed = key.trim()
  if (!trimmed) {
    getStore().clearKey('openai')
    return { ok: true, hasKey: false }
  }
  const result = await validate(trimmed)
  if (result.status === 401) {
    return { ok: false, hasKey: codexApiKeyStatus().hasKey, error: result.error }
  }
  getStore().setKey('openai', trimmed)
  return { ok: true, hasKey: true, warning: result.ok ? undefined : result.error }
}

/** Test seam: inject a fake backing store (no Electron safeStorage needed). */
export function __setCodexKeyStoreForTests(fake: CodexKeyBackingStore | null): void {
  store = fake
}
