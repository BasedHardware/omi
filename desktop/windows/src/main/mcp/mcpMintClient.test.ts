import { describe, it, expect, vi } from 'vitest'
import { mintMcpKey, listMcpKeys, deleteMcpKey } from './mcpMintClient'

const API = 'https://api.omi.me'
const TOKEN = 'firebase-id-token'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body)
  } as unknown as Response
}

describe('mintMcpKey', () => {
  it('POSTs {name} to /v1/mcp/keys with a bearer token and returns the raw key', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ id: 'k1', name: 'Omi Desktop', key: 'mcp_secret' })
    )
    const r = await mintMcpKey(API, TOKEN, 'Omi Desktop', fetchImpl as unknown as typeof fetch)
    expect(r).toEqual({ id: 'k1', name: 'Omi Desktop', key: 'mcp_secret' })
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('https://api.omi.me/v1/mcp/keys')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`)
    expect(JSON.parse(init.body)).toEqual({ name: 'Omi Desktop' })
  })

  it('throws when the response omits a key', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ id: 'k1', name: 'x' }))
    await expect(
      mintMcpKey(API, TOKEN, 'Omi Desktop', fetchImpl as unknown as typeof fetch)
    ).rejects.toThrow('no key')
  })

  it('surfaces a non-2xx status as an error', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ detail: 'nope' }, 402))
    await expect(
      mintMcpKey(API, TOKEN, 'Omi Desktop', fetchImpl as unknown as typeof fetch)
    ).rejects.toThrow('402')
  })
})

describe('listMcpKeys', () => {
  it('parses a bare array', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse([{ id: 'a', name: 'one' }, { id: 'b', name: 'two' }])
    )
    const r = await listMcpKeys(API, TOKEN, fetchImpl as unknown as typeof fetch)
    expect(r).toEqual([{ id: 'a', name: 'one' }, { id: 'b', name: 'two' }])
  })

  it('parses a {keys:[…]} envelope and skips rows without ids', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ keys: [{ id: 'a', name: 'one' }, { name: 'no-id' }] })
    )
    const r = await listMcpKeys(API, TOKEN, fetchImpl as unknown as typeof fetch)
    expect(r).toEqual([{ id: 'a', name: 'one' }])
  })
})

describe('deleteMcpKey', () => {
  it('DELETEs /v1/mcp/keys/{id}', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 204))
    await deleteMcpKey(API, TOKEN, 'k1', fetchImpl as unknown as typeof fetch)
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('https://api.omi.me/v1/mcp/keys/k1')
    expect(init.method).toBe('DELETE')
  })

  it('treats 404 as already-gone (idempotent)', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 404))
    await expect(
      deleteMcpKey(API, TOKEN, 'k1', fetchImpl as unknown as typeof fetch)
    ).resolves.toBeUndefined()
  })

  it('throws on other failures', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 500))
    await expect(
      deleteMcpKey(API, TOKEN, 'k1', fetchImpl as unknown as typeof fetch)
    ).rejects.toThrow('500')
  })
})
