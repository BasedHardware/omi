import { describe, it, expect, vi, afterEach } from 'vitest'

vi.mock('./firebase', () => ({
  auth: { currentUser: { getIdToken: async () => 'tok' } }
}))

import { generate } from './geminiClient'

afterEach(() => vi.unstubAllGlobals())

describe('generate', () => {
  it('retries when a 200 response body is not valid JSON, then succeeds', async () => {
    let n = 0
    const fetchMock = vi.fn(async () => {
      n++
      if (n === 1) {
        return {
          ok: true,
          json: async () => {
            throw new SyntaxError('truncated body')
          }
        }
      }
      return { ok: true, json: async () => ({ candidates: [{ content: { parts: [{ text: 'hello' }] } }] }) }
    })
    vi.stubGlobal('fetch', fetchMock)

    const out = await generate({ model: 'm', parts: [{ text: 'hi' }] })
    expect(out).toBe('hello')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('rejects with a sanitized message after a network error exhausts retries', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('ECONNREFUSED 10.0.0.1 secret')
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(generate({ model: 'm', parts: [{ text: 'hi' }] })).rejects.toThrow(/after retries/)
    await expect(generate({ model: 'm', parts: [{ text: 'hi' }] })).rejects.not.toThrow(/secret/)
  })
})
