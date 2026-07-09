import { describe, it, expect, vi, afterEach } from 'vitest'
import { BeeperClient, beeperTimestampMs } from './beeperClient'

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  })

afterEach(() => vi.unstubAllGlobals())

describe('BeeperClient', () => {
  it('sends the bearer token and parses {items:[…]} chat lists', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ items: [{ id: 'c1', title: 'Alice', network: 'WhatsApp', type: 'single' }] })
    )
    vi.stubGlobal('fetch', fetchMock)

    const r = await new BeeperClient('tok').listChats()
    expect(r).toEqual({
      ok: true,
      value: [{ id: 'c1', title: 'Alice', network: 'WhatsApp', type: 'single' }]
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:23373/v1/chats')
    expect(init.headers.Authorization).toBe('Bearer tok')
  })

  it('POSTs a send with text (and threads replyToMessageID when given)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ pendingMessageID: 'p1' }))
    vi.stubGlobal('fetch', fetchMock)

    const r = await new BeeperClient('tok').sendMessage('chat/1', 'hello', 'm9')
    expect(r).toEqual({ ok: true, value: { pendingMessageID: 'p1' } })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:23373/v1/chats/chat%2F1/messages')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ text: 'hello', replyToMessageID: 'm9' })
  })

  it('classifies 401 as unauthorized and connection failure as unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 401)))
    expect(await new BeeperClient('bad').validateToken()).toEqual({
      ok: false,
      error: 'unauthorized'
    })

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const r = await new BeeperClient('tok').validateToken()
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toBe('unreachable')
  })

  it('classifies other HTTP failures as http_error with detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 500)))
    const r = await new BeeperClient('tok').listMessages('c1')
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.error).toBe('http_error')
      expect(r.detail).toContain('500')
    }
  })
})

describe('beeperTimestampMs', () => {
  it('passes numbers through, parses ISO strings, rejects garbage', () => {
    expect(beeperTimestampMs(1739320000000)).toBe(1739320000000)
    expect(beeperTimestampMs('2025-02-12T00:00:00.000Z')).toBe(
      Date.parse('2025-02-12T00:00:00.000Z')
    )
    expect(beeperTimestampMs('not-a-date')).toBeUndefined()
    expect(beeperTimestampMs(undefined)).toBeUndefined()
  })
})
