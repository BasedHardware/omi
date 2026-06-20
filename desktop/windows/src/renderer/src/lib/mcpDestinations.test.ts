import { describe, expect, it, vi } from 'vitest'
import {
  buildHostedMcpHealthRequest,
  parseHostedMcpMemoryCount,
  testHostedMcpConnection
} from './mcpDestinations'

describe('hosted MCP health check', () => {
  it('builds the get_memories JSON-RPC request with bearer auth', () => {
    const { url, init } = buildHostedMcpHealthRequest('omi_secret')

    expect(url).toBe('https://api.omi.me/v1/mcp/sse')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer omi_secret'
    })
    expect(JSON.parse(String(init.body))).toEqual({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: 'get_memories',
        arguments: { limit: 5 }
      }
    })
  })

  it('parses the memory count from MCP text content', () => {
    expect(
      parseHostedMcpMemoryCount({
        result: {
          content: [
            { type: 'text', text: JSON.stringify({ memories: [{ id: '1' }, { id: '2' }] }) }
          ]
        }
      })
    ).toBe(2)
  })

  it('surfaces JSON-RPC errors without exposing the key', () => {
    expect(() =>
      parseHostedMcpMemoryCount({
        error: { message: 'Invalid or expired key' }
      })
    ).toThrow('Hosted MCP failed: Invalid or expired key')
  })

  it('reports HTTP failures precisely', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 })
    vi.stubGlobal('fetch', fetchMock)

    await expect(testHostedMcpConnection('omi_secret')).rejects.toThrow(
      'Hosted MCP returned HTTP 401.'
    )
    expect(fetchMock).toHaveBeenCalledOnce()

    vi.unstubAllGlobals()
  })
})
