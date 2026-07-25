// The setup-completion check drives Electron's net.fetch (Chromium network stack).
// Mock it the same way notion.test.ts does, then assert: https-only guard, the uid
// is appended, `is_setup_completed: true` → true, and every failure mode → false.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ fetch: vi.fn() }))

vi.mock('electron', () => ({
  net: { fetch: h.fetch },
  ipcMain: { handle: vi.fn() }
}))

import { checkAppSetup } from './checkAppSetup'

function ok(body: unknown): { ok: true; status: number; json: () => Promise<unknown> } {
  return { ok: true, status: 200, json: async () => body }
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

describe('checkAppSetup', () => {
  it('GETs the url with uid appended and returns true when is_setup_completed is true', async () => {
    h.fetch.mockResolvedValueOnce(ok({ is_setup_completed: true }))

    const result = await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'user-42' })

    expect(result).toBe(true)
    expect(h.fetch).toHaveBeenCalledTimes(1)
    const [reqUrl, init] = h.fetch.mock.calls[0]
    const parsed = new URL(reqUrl as string)
    expect(parsed.origin + parsed.pathname).toBe('https://dev.example.com/done')
    expect(parsed.searchParams.get('uid')).toBe('user-42')
    expect((init as { method: string }).method).toBe('GET')
  })

  it('preserves existing query params and overrides uid', async () => {
    h.fetch.mockResolvedValueOnce(ok({ is_setup_completed: true }))
    await checkAppSetup({ url: 'https://dev.example.com/done?foo=bar&uid=stale', uid: 'fresh' })
    const parsed = new URL(h.fetch.mock.calls[0][0] as string)
    expect(parsed.searchParams.get('foo')).toBe('bar')
    expect(parsed.searchParams.get('uid')).toBe('fresh')
  })

  it('returns false when is_setup_completed is false or absent', async () => {
    h.fetch.mockResolvedValueOnce(ok({ is_setup_completed: false }))
    expect(await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'u' })).toBe(false)
    h.fetch.mockResolvedValueOnce(ok({}))
    expect(await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'u' })).toBe(false)
  })

  it('returns false on a non-ok response', async () => {
    h.fetch.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) })
    expect(await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'u' })).toBe(false)
  })

  it('returns false and never fetches for a non-https url (https-only guard)', async () => {
    expect(await checkAppSetup({ url: 'http://dev.example.com/done', uid: 'u' })).toBe(false)
    expect(await checkAppSetup({ url: 'file:///etc/passwd', uid: 'u' })).toBe(false)
    expect(await checkAppSetup({ url: 'javascript:alert(1)', uid: 'u' })).toBe(false)
    expect(await checkAppSetup({ url: 'not a url', uid: 'u' })).toBe(false)
    expect(await checkAppSetup({ url: '', uid: 'u' })).toBe(false)
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('returns false when the fetch rejects (network error / abort)', async () => {
    h.fetch.mockRejectedValueOnce(new Error('network down'))
    expect(await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'u' })).toBe(false)
  })

  it('returns false when the body is not valid JSON', async () => {
    h.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error('invalid json')
      }
    })
    expect(await checkAppSetup({ url: 'https://dev.example.com/done', uid: 'u' })).toBe(false)
  })
})
