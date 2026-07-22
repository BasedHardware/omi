import { describe, it, expect } from 'vitest'
import { enrollByok, type BackendFetch } from './byokEnroll'
import type { FetchLike } from './byokValidator'
import { byokFingerprint } from '../../shared/byokFingerprint'
import type { ByokKeys } from '../../shared/byok'

const fullKeys: ByokKeys = {
  openai: 'sk-openai',
  anthropic: 'sk-ant',
  gemini: 'gm-key',
  deepgram: 'dg-key'
}

/** Validator fetch that returns a per-URL status (default 200). */
function validatorFetch(statusFor: (url: string) => number = () => 200): FetchLike {
  return async (url) => ({ status: statusFor(url) })
}

/** Backend fetch stub that records calls and returns a fixed ok/status. */
function backendStub(ok = true, status = 200): {
  fetch: BackendFetch
  calls: { url: string; method: string; headers: Record<string, string>; body?: string }[]
} {
  const calls: { url: string; method: string; headers: Record<string, string>; body?: string }[] = []
  const fetch: BackendFetch = async (url, init) => {
    calls.push({ url, method: init.method, headers: init.headers, body: init.body })
    return { ok, status }
  }
  return { fetch, calls }
}

describe('enrollByok', () => {
  it('POSTs lowercase-hex-64 fingerprints and activates when all four validate', async () => {
    const backend = backendStub()
    const result = await enrollByok({
      keys: fullKeys,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: validatorFetch(),
      backendFetch: backend.fetch
    })
    expect(result.active).toBe(true)
    expect(backend.calls).toHaveLength(1)
    const [call] = backend.calls
    expect(call.method).toBe('POST')
    expect(call.url).toBe('https://api.omi.me/v1/users/me/byok-active')
    const body = JSON.parse(call.body as string)
    expect(Object.keys(body.fingerprints).sort()).toEqual([
      'anthropic',
      'deepgram',
      'gemini',
      'openai'
    ])
    for (const fp of Object.values(body.fingerprints)) {
      expect(fp).toMatch(/^[a-f0-9]{64}$/)
    }
    // Fingerprints are the SHA-256 of the trimmed raw keys.
    expect(body.fingerprints.openai).toBe(byokFingerprint('sk-openai'))
  })

  it('never sends X-BYOK-* headers on the enrollment call (only the bearer token)', async () => {
    const backend = backendStub()
    await enrollByok({
      keys: fullKeys,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: validatorFetch(),
      backendFetch: backend.fetch
    })
    const headerNames = Object.keys(backend.calls[0].headers)
    expect(headerNames.some((h) => h.toLowerCase().startsWith('x-byok'))).toBe(false)
    expect(backend.calls[0].headers.Authorization).toBe('Bearer tok')
  })

  it('does not validate and DELETEs (deactivates) when the set is not full', async () => {
    const backend = backendStub()
    let validatorCalled = false
    const validate: FetchLike = async () => {
      validatorCalled = true
      return { status: 200 }
    }
    const partial: ByokKeys = { openai: 'a', anthropic: 'b', gemini: 'c' }
    const result = await enrollByok({
      keys: partial,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: validate,
      backendFetch: backend.fetch
    })
    expect(result.active).toBe(false)
    expect(result.results).toEqual({})
    expect(validatorCalled).toBe(false)
    expect(backend.calls).toHaveLength(1)
    expect(backend.calls[0].method).toBe('DELETE')
  })

  it('DELETEs and reports the rejecting provider when one key is rejected', async () => {
    const backend = backendStub()
    const result = await enrollByok({
      keys: fullKeys,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: validatorFetch((url) => (url.includes('anthropic') ? 401 : 200)),
      backendFetch: backend.fetch
    })
    expect(result.active).toBe(false)
    expect(result.results.anthropic).toMatchObject({ ok: false, kind: 'rejected' })
    expect(result.results.openai?.ok).toBe(true)
    expect(backend.calls).toHaveLength(1)
    expect(backend.calls[0].method).toBe('DELETE')
  })

  it('reports a backendError (not active) when keys validate but the enroll POST fails', async () => {
    const backend = backendStub(false, 502)
    const result = await enrollByok({
      keys: fullKeys,
      apiBase: 'https://api.omi.me',
      token: 'tok',
      validateFetch: validatorFetch(),
      backendFetch: backend.fetch
    })
    expect(result.active).toBe(false)
    expect(result.backendError).toContain('502')
    // Keys still validated OK — the failure is the backend call, not the keys.
    expect(result.results.openai?.ok).toBe(true)
    expect(backend.calls[0].method).toBe('POST')
  })

  it('trims a trailing slash on the api base', async () => {
    const backend = backendStub()
    await enrollByok({
      keys: fullKeys,
      apiBase: 'https://api.omi.me/',
      token: 'tok',
      validateFetch: validatorFetch(),
      backendFetch: backend.fetch
    })
    expect(backend.calls[0].url).toBe('https://api.omi.me/v1/users/me/byok-active')
  })
})
