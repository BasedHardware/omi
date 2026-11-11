// The MCP stdio server's protocol layer — transport-free unit tests.
//
// `createMcpServer` is exported from the shipped `.mjs` entry precisely so the
// JSON-RPC handling can be driven without spawning a subprocess or opening a
// socket: `askHost` and `send` are injected. These tests pin the protocol
// contract AND the one security-relevant property of this layer — that it does
// NOT filter tool names. An unadvertised name must reach the host, because the
// host's dispatch gate is the only place a rejection is a real gate; filtering
// here would be security theatre that hides the gate rather than enforcing it.

import { describe, expect, it, vi } from 'vitest'
import { createMcpServer } from './omi-mcp-entry.mjs'

type JsonRpc = {
  jsonrpc: string
  id?: unknown
  result?: Record<string, unknown>
  error?: { code: number; message: string }
}

function harness(askHost: (frame: Record<string, unknown>) => Promise<unknown>): {
  handleLine: (line: string) => Promise<void>
  sent: JsonRpc[]
} {
  const sent: JsonRpc[] = []
  const server = createMcpServer({ askHost, send: (message: JsonRpc) => sent.push(message) })
  return { handleLine: server.handleLine, sent }
}

const okList = async (): Promise<unknown> => ({ type: 'list_result', tools: [{ name: 'x' }] })

describe('MCP protocol handshake', () => {
  it('answers initialize with the protocol version and server info', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize' }))
    expect(sent).toHaveLength(1)
    expect(sent[0].result?.serverInfo).toMatchObject({ name: 'omi' })
    expect(sent[0].result?.protocolVersion).toBeTruthy()
  })

  it('ignores the initialized notification (no id, no response)', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }))
    expect(sent).toHaveLength(0)
  })

  it('never responds to a notification, even for a known method', async () => {
    const { handleLine, sent } = harness(okList)
    // initialize with no id is a notification — it takes no response.
    await handleLine(JSON.stringify({ jsonrpc: '2.0', method: 'initialize' }))
    expect(sent).toHaveLength(0)
  })
})

describe('tools/list', () => {
  it('relays the host tool list verbatim', async () => {
    const askHost = vi.fn(okList)
    const { handleLine, sent } = harness(askHost)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }))
    expect(askHost).toHaveBeenCalledWith({ type: 'list' })
    expect(sent[0].result?.tools).toEqual([{ name: 'x' }])
  })
})

describe('tools/call', () => {
  it('forwards name + arguments to the host and wraps the result as MCP content', async () => {
    const askHost = vi.fn(async () => ({ type: 'call_result', result: '{"ok":true}' }))
    const { handleLine, sent } = harness(askHost)
    await handleLine(
      JSON.stringify({
        jsonrpc: '2.0',
        id: 3,
        method: 'tools/call',
        params: { name: 'list_agent_sessions', arguments: { ownerId: 'o' } }
      })
    )
    expect(askHost).toHaveBeenCalledWith({
      type: 'call',
      name: 'list_agent_sessions',
      input: { ownerId: 'o' }
    })
    expect(sent[0].result?.content).toEqual([{ type: 'text', text: '{"ok":true}' }])
  })

  it('does NOT filter an unadvertised tool name — it reaches the host for dispatch', async () => {
    const askHost = vi.fn(async () => ({ type: 'call_result', result: '{"ok":false}' }))
    const { handleLine } = harness(askHost)
    await handleLine(
      JSON.stringify({
        jsonrpc: '2.0',
        id: 4,
        method: 'tools/call',
        params: { name: 'spawn_background_agent', arguments: {} }
      })
    )
    // The whole security model depends on this: the client is not a gate.
    expect(askHost).toHaveBeenCalledWith({
      type: 'call',
      name: 'spawn_background_agent',
      input: {}
    })
  })

  it('rejects a tools/call with no tool name', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', id: 5, method: 'tools/call', params: {} }))
    expect(sent[0].error?.code).toBe(-32602)
  })

  it('returns a transport error if the host relay throws', async () => {
    const askHost = vi.fn(async () => {
      throw new Error('host connection closed')
    })
    const { handleLine, sent } = harness(askHost)
    await handleLine(
      JSON.stringify({
        jsonrpc: '2.0',
        id: 6,
        method: 'tools/call',
        params: { name: 'list_agent_sessions', arguments: {} }
      })
    )
    expect(sent[0].error?.code).toBe(-32603)
    expect(sent[0].error?.message).toMatch(/host connection closed/)
  })
})

describe('hostile / malformed input never throws', () => {
  it('unparseable JSON gets a parse error with a null id', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine('{ this is not json')
    expect(sent[0].error?.code).toBe(-32700)
    expect(sent[0].id).toBeNull()
  })

  it('a JSON array (not an object) is an invalid request', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify([1, 2, 3]))
    expect(sent[0].error?.code).toBe(-32600)
  })

  it('a blank line is ignored', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine('   ')
    expect(sent).toHaveLength(0)
  })

  it('an unknown method returns method-not-found', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', id: 7, method: 'resources/list' }))
    expect(sent[0].error?.code).toBe(-32601)
  })

  it('a request whose method is not a string is an invalid request', async () => {
    const { handleLine, sent } = harness(okList)
    await handleLine(JSON.stringify({ jsonrpc: '2.0', id: 8, method: 42 }))
    expect(sent[0].error?.code).toBe(-32600)
  })
})
