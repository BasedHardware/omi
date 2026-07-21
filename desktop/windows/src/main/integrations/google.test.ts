import { describe, it, expect, vi, afterEach } from 'vitest'

vi.mock('./oauth', () => ({
  getAccessToken: async () => 'tok',
  invalidateAccessToken: () => {}
}))

import { fetchGmail } from './google'

afterEach(() => vi.unstubAllGlobals())

describe('fetchGmail', () => {
  it('skips a message that fails to fetch and keeps the rest of the batch', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/messages?q=')) {
        return { ok: true, status: 200, json: async () => ({ messages: [{ id: 'a' }, { id: 'b' }] }) }
      }
      if (url.includes('/messages/a')) {
        return { ok: false, status: 500, text: async () => 'boom' }
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ id: 'b', payload: { headers: [{ name: 'Subject', value: 'Hi' }] } })
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    const items = await fetchGmail()
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('b')
    expect(items[0].subject).toBe('Hi')
  })
})
