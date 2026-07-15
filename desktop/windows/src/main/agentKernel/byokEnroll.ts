// BYOK enrollment orchestrator (main process, Electron-free so it unit-tests
// without safeStorage/ipc). Ports the macOS `refreshBYOKActivation` state
// machine: on any key change the client live-validates the full set and either
// enrolls the user onto the BYOK free plan or takes them off it. We never flip
// the backend on with a dead key.
//
// Backend contract (backend/routers/users.py):
//   POST   /v1/users/me/byok-active  { fingerprints: {openai,anthropic,gemini,deepgram} }
//   DELETE /v1/users/me/byok-active
// Fingerprints are lowercase-hex SHA-256 of the trimmed keys; the raw keys are
// NEVER sent to this endpoint (they travel as X-BYOK-* headers on other
// requests). The endpoint authenticates via the Firebase bearer token only and
// must NOT carry X-BYOK-* headers itself.

import { validateAllByokKeys, type FetchLike } from './byokValidator'
import { byokFingerprint } from '../../shared/byokFingerprint'
import {
  BYOK_PROVIDERS,
  isByokActive,
  type ByokEnrollResult,
  type ByokKeys
} from '../../shared/byok'

export type { ByokEnrollResult } from '../../shared/byok'

/** The subset of `fetch` the backend enroll/deactivate calls depend on. */
export type BackendFetch = (
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string }
) => Promise<{ ok: boolean; status: number }>

const ENROLL_PATH = '/v1/users/me/byok-active'

function enrollUrl(apiBase: string): string {
  return `${apiBase.replace(/\/+$/, '')}${ENROLL_PATH}`
}

async function postActivate(
  apiBase: string,
  token: string,
  fingerprints: Record<string, string>,
  fetchImpl: BackendFetch
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetchImpl(enrollUrl(apiBase), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'X-App-Platform': 'windows'
      },
      body: JSON.stringify({ fingerprints })
    })
    return res.ok ? { ok: true } : { ok: false, error: `HTTP ${res.status}` }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'network error' }
  }
}

async function deleteActivate(apiBase: string, token: string, fetchImpl: BackendFetch): Promise<void> {
  try {
    await fetchImpl(enrollUrl(apiBase), {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}`, 'X-App-Platform': 'windows' }
    })
  } catch {
    // Best-effort: if we can't reach the backend to deactivate, the client-side
    // keys are already gone/incomplete so nothing will send a valid BYOK set;
    // the heartbeat TTL also lapses the activation server-side.
  }
}

/**
 * Validate the current key set and reconcile the backend BYOK activation.
 *
 * - Not all four present → never validate; ensure the backend is OFF; no results.
 * - All four present → live-validate all in parallel:
 *   - all authenticate → POST fingerprints (active) unless the backend call fails.
 *   - any fail → DELETE (inactive) and return the per-key results so the UI can
 *     show which provider rejected.
 */
export async function enrollByok(opts: {
  keys: ByokKeys
  apiBase: string
  token: string
  /** Injectable in tests; defaults to the validator's own global fetch. */
  validateFetch?: FetchLike
  /** Injectable in tests; defaults to global fetch. */
  backendFetch?: BackendFetch
}): Promise<ByokEnrollResult> {
  const { keys, apiBase, token } = opts
  const backendFetch = opts.backendFetch ?? (globalThis.fetch as unknown as BackendFetch)

  if (!isByokActive(keys)) {
    await deleteActivate(apiBase, token, backendFetch)
    return { active: false, results: {} }
  }

  const results = await validateAllByokKeys(keys, opts.validateFetch)
  const allOk = BYOK_PROVIDERS.every((p) => results[p]?.ok)
  if (!allOk) {
    await deleteActivate(apiBase, token, backendFetch)
    return { active: false, results }
  }

  const fingerprints: Record<string, string> = {}
  for (const p of BYOK_PROVIDERS) fingerprints[p] = byokFingerprint(keys[p] as string)
  const posted = await postActivate(apiBase, token, fingerprints, backendFetch)
  if (!posted.ok) return { active: false, results, backendError: posted.error }
  return { active: true, results }
}
