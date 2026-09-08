// Unit tests for the main-side backend tool client (backendToolFetch). electron
// `net` and the shared session are mocked; we assert URL/query/body/header
// construction, the fail-open Error strings, and the result_text relay.

import { describe, it, expect, vi, beforeEach } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  session: null as { apiBase: string; token: string } | null,
  abortSignal: undefined as AbortSignal | undefined
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../assistants/core/session', () => ({
  getBackendSession: () => h.session,
  getAbortSignal: () => h.abortSignal
}))

import { backendToolFetch } from './backendTools'

function okResponse(body: unknown, status = 200): unknown {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

beforeEach(() => {
  h.fetch.mockReset()
  h.session = { apiBase: 'https://api.omi.test', token: 'tok-123' }
  h.abortSignal = undefined
})

describe('backendToolFetch', () => {
  it('returns a signed-out error when there is no session', async () => {
    h.session = null
    const out = await backendToolFetch({ method: 'GET', path: '/v1/tools/memories' })
    expect(out).toContain('not signed in')
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('GETs with query params, Bearer auth, and relays result_text', async () => {
    h.fetch.mockResolvedValue(
      okResponse({ tool_name: 'get_memories', result_text: 'you like tea', is_error: false })
    )
    const out = await backendToolFetch({
      method: 'GET',
      path: '/v1/tools/memories',
      query: { limit: 50, offset: 0, start_date: undefined }
    })
    expect(out).toBe('you like tea')
    const [url, init] = h.fetch.mock.calls[0]
    expect(url).toBe('https://api.omi.test/v1/tools/memories?limit=50&offset=0')
    expect(url).not.toContain('start_date') // undefined dropped
    expect(init.method).toBe('GET')
    expect(init.headers.Authorization).toBe('Bearer tok-123')
  })

  it('POSTs a JSON body with Content-Type', async () => {
    h.fetch.mockResolvedValue(okResponse({ result_text: 'hits' }))
    const out = await backendToolFetch({
      method: 'POST',
      path: '/v1/tools/memories/search',
      body: { query: 'dog', limit: 5 }
    })
    expect(out).toBe('hits')
    const [, init] = h.fetch.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ query: 'dog', limit: 5 })
  })

  it('maps a non-2xx status to an Error string', async () => {
    h.fetch.mockResolvedValue(okResponse({}, 500))
    const out = await backendToolFetch({ method: 'GET', path: '/v1/tools/memories' })
    expect(out).toBe('Error: backend tool request failed (HTTP 500)')
  })

  it('returns "No results." on an empty result_text', async () => {
    h.fetch.mockResolvedValue(okResponse({ tool_name: 'get_memories', result_text: '' }))
    const out = await backendToolFetch({ method: 'GET', path: '/v1/tools/memories' })
    expect(out).toBe('No results.')
  })

  it('fails open to an Error string when fetch throws', async () => {
    h.fetch.mockRejectedValue(new Error('network down'))
    const out = await backendToolFetch({ method: 'GET', path: '/v1/tools/memories' })
    expect(out).toContain('Error: network down')
  })

  it('does not call fetch when the caller signal is already aborted', async () => {
    const ac = new AbortController()
    ac.abort()
    const out = await backendToolFetch({
      method: 'GET',
      path: '/v1/tools/memories',
      signal: ac.signal
    })
    expect(out).toContain('cancelled')
    expect(h.fetch).not.toHaveBeenCalled()
  })
})
