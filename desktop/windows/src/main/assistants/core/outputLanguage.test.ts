import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  session: { apiBase: 'https://api.test', token: 'tok' } as {
    apiBase: string
    token: string
  } | null
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('./session', () => ({
  getAbortSignal: () => undefined,
  getBackendSession: () => h.session
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
  it('caches a successful read for an hour and retries after a failure', async () => {
    respond('es')
    expect(await getUserLanguage(0)).toBe('es')
    expect(await getUserLanguage(59 * 60_000)).toBe('es')
    expect(h.fetch).toHaveBeenCalledTimes(1)

    respond('fr')
    expect(await getUserLanguage(61 * 60_000)).toBe('fr')
    expect(h.fetch).toHaveBeenCalledTimes(2)

    resetUserLanguageCache()
    h.fetch.mockResolvedValue({ ok: false })
    expect(await getUserLanguage(0)).toBeNull()
    respond('de')
    expect(await getUserLanguage(1)).toBe('de')
  })
})
