import { createHash } from 'crypto'
import { apiRequest } from './apiProxy'
import { settings } from './settings'
import { getByokKeys } from './secrets'

// Bring-Your-Own-Keys activation. The desktop backend's paywall (paywall.rs) has a
// BYOK escape hatch: a user enrolled on the "BYOK free plan" with all four provider
// keys is never paywalled (they pay the providers directly). Enrollment = POST the
// SHA-256 fingerprints of the four keys to /v1/users/me/byok-active; thereafter the
// app sends the X-BYOK-* headers (apiProxy already does) which the backend matches
// against the enrolled fingerprints.

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'deepgram'] as const

function fingerprint(key: string): string {
  return createHash('sha256').update(key.trim(), 'utf8').digest('hex')
}

export interface ByokActivateResult {
  ok: boolean
  error?: string
  missing?: string[]
}

export async function activateByok(): Promise<ByokActivateResult> {
  const k = getByokKeys()
  const keys: Record<string, string> = {
    openai: k.openai.trim(),
    anthropic: k.anthropic.trim(),
    gemini: k.gemini.trim(),
    deepgram: k.deepgram.trim()
  }
  const missing = PROVIDERS.filter((p) => !keys[p])
  if (missing.length) return { ok: false, missing }

  const fingerprints: Record<string, string> = {}
  for (const p of PROVIDERS) fingerprints[p] = fingerprint(keys[p])

  const res = await apiRequest({
    method: 'POST',
    url: 'v1/users/me/byok-active',
    base: 'python',
    body: JSON.stringify({ fingerprints })
  })
  if (res.status >= 200 && res.status < 300) {
    settings.set({ byokActive: true })
    return { ok: true }
  }
  return { ok: false, error: `HTTP ${res.status}: ${res.body.slice(0, 200)}` }
}

export async function deactivateByok(): Promise<ByokActivateResult> {
  const res = await apiRequest({ method: 'DELETE', url: 'v1/users/me/byok-active', base: 'python' })
  if (res.status >= 200 && res.status < 300) {
    settings.set({ byokActive: false })
    return { ok: true }
  }
  return { ok: false, error: `HTTP ${res.status}` }
}
