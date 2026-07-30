import { describe, it, expect, vi } from 'vitest'
import {
  validateProviderKey,
  validateAllByokKeys,
  type FetchLike
} from './byokValidator'
import type { ByokKeys } from '../../shared/byok'

/** A FetchLike that returns a fixed status and records the calls it received. */
function stubFetch(status: number): { fetch: FetchLike; calls: { url: string; headers: Record<string, string> }[] } {
  const calls: { url: string; headers: Record<string, string> }[] = []
  const fetch: FetchLike = async (url, init) => {
    calls.push({ url, headers: init.headers })
    return { status }
  }
  return { fetch, calls }
}

describe('validateProviderKey — classifier', () => {
  it('treats 200 as ok', async () => {
    const { fetch } = stubFetch(200)
    expect(await validateProviderKey('openai', 'sk-x', fetch)).toEqual({ ok: true })
  })

  it('treats other 2xx as ok', async () => {
    const { fetch } = stubFetch(204)
    expect((await validateProviderKey('deepgram', 'dg', fetch)).ok).toBe(true)
  })

  it('classifies 401 as a provider rejection', async () => {
    const { fetch } = stubFetch(401)
    const r = await validateProviderKey('anthropic', 'bad', fetch)
    expect(r).toMatchObject({ ok: false, kind: 'rejected' })
    expect(r.detail).toContain('401')
  })

  it('classifies 403 as a provider rejection', async () => {
    const { fetch } = stubFetch(403)
    expect(await validateProviderKey('gemini', 'bad', fetch)).toMatchObject({
      ok: false,
      kind: 'rejected'
    })
  })

  it('classifies a 500 as a transient http failure (not a rejection)', async () => {
    const { fetch } = stubFetch(500)
    expect(await validateProviderKey('openai', 'sk', fetch)).toMatchObject({
      ok: false,
      kind: 'http'
    })
  })

  it('classifies a thrown network error', async () => {
    const fetch: FetchLike = async () => {
      throw new Error('ECONNREFUSED')
    }
    expect(await validateProviderKey('openai', 'sk', fetch)).toMatchObject({
      ok: false,
      kind: 'network'
    })
  })

  it('classifies an AbortError as a timeout', async () => {
    const fetch: FetchLike = async () => {
      const e = new Error('aborted')
      e.name = 'AbortError'
      throw e
    }
    expect(await validateProviderKey('openai', 'sk', fetch)).toMatchObject({
      ok: false,
      kind: 'timeout'
    })
  })

  it('fails an empty/whitespace key without making a request', async () => {
    const { fetch, calls } = stubFetch(200)
    expect(await validateProviderKey('openai', '   ', fetch)).toMatchObject({
      ok: false,
      kind: 'empty'
    })
    expect(calls).toHaveLength(0)
  })

  it('never sends a Bearer prefix in the validated value and trims the key', async () => {
    const { fetch, calls } = stubFetch(200)
    await validateProviderKey('openai', '  sk-trim  ', fetch)
    expect(calls[0].headers.Authorization).toBe('Bearer sk-trim')
  })

  it('uses the documented per-provider endpoint + auth header', async () => {
    const openai = stubFetch(200)
    await validateProviderKey('openai', 'k', openai.fetch)
    expect(openai.calls[0].url).toBe('https://api.openai.com/v1/models')
    expect(openai.calls[0].headers.Authorization).toBe('Bearer k')

    const anthropic = stubFetch(200)
    await validateProviderKey('anthropic', 'k', anthropic.fetch)
    expect(anthropic.calls[0].url).toContain('api.anthropic.com/v1/models?limit=1')
    expect(anthropic.calls[0].headers['x-api-key']).toBe('k')
    expect(anthropic.calls[0].headers['anthropic-version']).toBe('2023-06-01')

    const gemini = stubFetch(200)
    await validateProviderKey('gemini', 'k', gemini.fetch)
    expect(gemini.calls[0].url).toContain('generativelanguage.googleapis.com/v1beta/models?key=k')

    const deepgram = stubFetch(200)
    await validateProviderKey('deepgram', 'k', deepgram.fetch)
    expect(deepgram.calls[0].url).toBe('https://api.deepgram.com/v1/projects')
    expect(deepgram.calls[0].headers.Authorization).toBe('Token k')
  })
})

describe('validateAllByokKeys', () => {
  it('validates all four providers in parallel and keys the results', async () => {
    const fullKeys: ByokKeys = { openai: 'a', anthropic: 'b', gemini: 'c', deepgram: 'd' }
    const { fetch, calls } = stubFetch(200)
    const results = await validateAllByokKeys(fullKeys, fetch)
    expect(calls).toHaveLength(4)
    expect(results.openai?.ok).toBe(true)
    expect(results.anthropic?.ok).toBe(true)
    expect(results.gemini?.ok).toBe(true)
    expect(results.deepgram?.ok).toBe(true)
  })

  it('marks a missing provider as an empty failure (no request for it)', async () => {
    const partial: ByokKeys = { openai: 'a', anthropic: 'b', gemini: 'c' }
    const fetch = vi.fn(async () => ({ status: 200 })) as unknown as FetchLike
    const results = await validateAllByokKeys(partial, fetch)
    expect(results.deepgram).toMatchObject({ ok: false, kind: 'empty' })
    expect(results.openai?.ok).toBe(true)
  })

  it('reports a per-provider rejection without failing the others', async () => {
    const fetch: FetchLike = async (url) => ({
      status: url.includes('anthropic') ? 401 : 200
    })
    const results = await validateAllByokKeys(
      { openai: 'a', anthropic: 'bad', gemini: 'c', deepgram: 'd' },
      fetch
    )
    expect(results.anthropic).toMatchObject({ ok: false, kind: 'rejected' })
    expect(results.openai?.ok).toBe(true)
    expect(results.gemini?.ok).toBe(true)
  })
})
