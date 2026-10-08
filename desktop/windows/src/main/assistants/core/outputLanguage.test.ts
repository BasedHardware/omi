import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  session: { apiBase: 'https://api.test', token: 'tok' } as {
    apiBase: string
    token: string
  } | null,
  epoch: 1
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('./session', () => ({
  getAbortSignal: () => undefined,
  getBackendSession: () => h.session,
  getSessionEpoch: () => h.epoch
}))

import {
  getUserLanguage,
  outputLanguageInstruction,
  resetUserLanguageCache,
  withOutputLanguage
} from './outputLanguage'

const respond = (language: string | null): void => {
  h.fetch.mockResolvedValue({ ok: true, json: async () => ({ language }) })
}

beforeEach(() => {
  resetUserLanguageCache()
  h.fetch.mockReset()
  h.session = { apiBase: 'https://api.test', token: 'tok' }
  h.epoch = 1
})

describe('outputLanguageInstruction', () => {
  it('names the language for non-English codes', () => {
    expect(outputLanguageInstruction('es')).toContain('Spanish (es)')
    expect(outputLanguageInstruction('pt-BR')).toContain('Portuguese (pt-BR)')
    expect(outputLanguageInstruction('sw')).toContain('in sw (sw)')
  })

  it('is null for English, multi, and unset', () => {
    for (const code of ['en', 'en-GB', 'multi', '', '  ', null, undefined]) {
      expect(outputLanguageInstruction(code)).toBeNull()
    }
  })
})

describe('withOutputLanguage', () => {
  it('appends the instruction for a Spanish account', async () => {
    respond('es')
    const prompt = await withOutputLanguage('BASE')
    expect(prompt.startsWith('BASE\n\nIMPORTANT:')).toBe(true)
    expect(prompt).toContain('Spanish (es)')
  })

  it('leaves the prompt unchanged for English, signed-out, and failed lookups', async () => {
    respond('en')
    expect(await withOutputLanguage('BASE')).toBe('BASE')

    resetUserLanguageCache()
    h.session = null
    expect(await withOutputLanguage('BASE')).toBe('BASE')

    h.session = { apiBase: 'https://api.test', token: 'tok' }
    h.fetch.mockRejectedValue(new Error('offline'))
    expect(await withOutputLanguage('BASE')).toBe('BASE')
  })
})

describe('getUserLanguage', () => {
  it('caches a successful read for an hour', async () => {
    respond('es')
    expect(await getUserLanguage(0)).toBe('es')
    expect(await getUserLanguage(59 * 60_000)).toBe('es')
    expect(h.fetch).toHaveBeenCalledTimes(1)

    respond('fr')
    expect(await getUserLanguage(61 * 60_000)).toBe('fr')
    expect(h.fetch).toHaveBeenCalledTimes(2)
  })

  it('remembers a failed lookup for a minute instead of retrying on every run', async () => {
    h.fetch.mockResolvedValue({ ok: false })
    expect(await getUserLanguage(0)).toBeNull()
    respond('de')
    expect(await getUserLanguage(30_000)).toBeNull()
    expect(h.fetch).toHaveBeenCalledTimes(1)
    expect(await getUserLanguage(61_000)).toBe('de')
    expect(h.fetch).toHaveBeenCalledTimes(2)

    resetUserLanguageCache()
    h.fetch.mockReset().mockRejectedValue(new Error('timeout'))
    expect(await getUserLanguage(0)).toBeNull()
    expect(await getUserLanguage(10_000)).toBeNull()
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })

  it('never serves the previous account’s language after a session change', async () => {
    respond('es')
    expect(await getUserLanguage(0)).toBe('es')
    h.epoch = 2 // setBackendSession: another account signed in
    respond('en')
    expect(await getUserLanguage(1_000)).toBe('en')
    expect(h.fetch).toHaveBeenCalledTimes(2)
  })

  it('does not file a lookup that finished after a session change under the new account', async () => {
    let land: (v: unknown) => void = () => {}
    h.fetch.mockReturnValueOnce(new Promise((r) => (land = r)))
    const stale = getUserLanguage(0)
    h.epoch = 2
    land({ ok: true, json: async () => ({ language: 'es' }) })
    expect(await stale).toBe('es')
    respond('en')
    expect(await getUserLanguage(1_000)).toBe('en')
  })

  it('shares one request between assistants asking at the same time', async () => {
    let land: (v: unknown) => void = () => {}
    h.fetch.mockReturnValueOnce(new Promise((r) => (land = r)))
    const calls = Array.from({ length: 5 }, () => getUserLanguage(0))
    land({ ok: true, json: async () => ({ language: 'es' }) })
    expect(await Promise.all(calls)).toEqual(['es', 'es', 'es', 'es', 'es'])
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })
})
