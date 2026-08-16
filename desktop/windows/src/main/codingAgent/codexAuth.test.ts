import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  __setCodexKeyStoreForTests,
  codexApiKeyStatus,
  getCodexApiKey,
  saveCodexApiKey,
  validateOpenAiKey,
  type FetchLike
} from './codexAuth'
import type { ByokProvider } from '../../shared/byok'

/** In-memory stand-in for ByokKeyStore's get/set/clear (no Electron safeStorage). */
function makeFakeStore(initial: Partial<Record<ByokProvider, string>> = {}) {
  const data: Partial<Record<ByokProvider, string>> = { ...initial }
  return {
    getKey: vi.fn((p: ByokProvider) => data[p] ?? null),
    setKey: vi.fn((p: ByokProvider, k: string) => {
      data[p] = k.trim()
    }),
    clearKey: vi.fn((p: ByokProvider) => {
      delete data[p]
    })
  }
}

afterEach(() => __setCodexKeyStoreForTests(null))

const okFetch =
  (status: number): FetchLike =>
  async () => ({ status })

describe('validateOpenAiKey', () => {
  it('accepts a 200', async () => {
    expect(await validateOpenAiKey('sk-good', okFetch(200))).toEqual({ ok: true, status: 200 })
  })
  it('rejects a 401 with a clear message', async () => {
    const r = await validateOpenAiKey('sk-bad', okFetch(401))
    expect(r.ok).toBe(false)
    expect(r.status).toBe(401)
    expect(r.error).toMatch(/rejected/i)
  })
  it('marks an unreachable network', async () => {
    const throwing: FetchLike = async () => {
      throw new Error('network down')
    }
    const r = await validateOpenAiKey('sk-x', throwing)
    expect(r).toMatchObject({ ok: false, unreachable: true })
  })
  it('refuses a blank key without a network call', async () => {
    const fetchImpl = vi.fn<FetchLike>()
    const r = await validateOpenAiKey('   ', fetchImpl)
    expect(r.ok).toBe(false)
    expect(fetchImpl).not.toHaveBeenCalled()
  })
})

describe('saveCodexApiKey', () => {
  it('stores a validated key and reports it present', async () => {
    const store = makeFakeStore()
    __setCodexKeyStoreForTests(store)
    const r = await saveCodexApiKey('  sk-good  ', async () => ({ ok: true, status: 200 }))
    expect(r).toEqual({ ok: true, hasKey: true, warning: undefined })
    expect(store.setKey).toHaveBeenCalledWith('openai', 'sk-good')
    expect(getCodexApiKey()).toBe('sk-good')
    expect(codexApiKeyStatus()).toEqual({ hasKey: true })
  })

  it('does NOT store a key OpenAI rejected (401)', async () => {
    const store = makeFakeStore()
    __setCodexKeyStoreForTests(store)
    const r = await saveCodexApiKey('sk-bad', async () => ({
      ok: false,
      status: 401,
      error: 'nope'
    }))
    expect(r.ok).toBe(false)
    expect(store.setKey).not.toHaveBeenCalled()
  })

  it('stores anyway when OpenAI is unreachable, with a soft warning', async () => {
    const store = makeFakeStore()
    __setCodexKeyStoreForTests(store)
    const r = await saveCodexApiKey('sk-offline', async () => ({
      ok: false,
      unreachable: true,
      error: 'Could not reach OpenAI to verify the key.'
    }))
    expect(r.ok).toBe(true)
    expect(r.hasKey).toBe(true)
    expect(r.warning).toMatch(/reach/i)
    expect(store.setKey).toHaveBeenCalledWith('openai', 'sk-offline')
  })

  it('clears the key when saved blank', async () => {
    const store = makeFakeStore({ openai: 'sk-old' })
    __setCodexKeyStoreForTests(store)
    const r = await saveCodexApiKey('   ')
    expect(r).toEqual({ ok: true, hasKey: false })
    expect(store.clearKey).toHaveBeenCalledWith('openai')
  })
})
