import { createServer, type Server } from 'http'
import { mkdtempSync, rmSync } from 'fs'
import { connect } from 'net'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LOCAL_AGENT_DEFAULT_PORT, setLocalAgentSettings } from './settings'
import {
  startLocalAgentServer,
  startLocalAgentServerIfEnabled,
  stopLocalAgentServer
} from './server'

const electronState = vi.hoisted(() => ({
  userData: '',
  encryptionAvailable: true
}))

vi.mock('electron', () => ({
  app: {
    getName: (): string => 'Omi Windows',
    getVersion: (): string => '1.2.3',
    getPath: (name: string): string => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`)
      return electronState.userData
    }
  },
  safeStorage: {
    isEncryptionAvailable: (): boolean => electronState.encryptionAvailable,
    encryptString: (value: string): Buffer => Buffer.from(`encrypted:${value}`, 'utf8'),
    decryptString: (value: Buffer): string => value.toString('utf8').replace(/^encrypted:/, '')
  }
}))

function listen(server: Server, port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => resolve())
  })
}

function close(server: Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) reject(error)
      else resolve()
    })
  })
}

function rawRequest(port: number, request: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const socket = connect(port, '127.0.0.1')
    let response = ''
    socket.setEncoding('utf8')
    socket.once('connect', () => socket.write(request))
    socket.on('data', (chunk) => {
      response += chunk
    })
    socket.once('end', () => resolve(response))
    socket.once('error', reject)
  })
}

describe('local agent server', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-local-agent-'))
    electronState.encryptionAvailable = true
  })

  afterEach(async () => {
    await stopLocalAgentServer()
    rmSync(electronState.userData, { recursive: true, force: true })
  })

  it('does not start until the local agent setting is enabled', async () => {
    await expect(startLocalAgentServerIfEnabled()).resolves.toBeNull()

    setLocalAgentSettings({ enabled: true, port: 47820 })
    const info = await startLocalAgentServerIfEnabled()

    expect(info).toMatchObject({
      host: '127.0.0.1',
      port: 47820,
      localUrl: 'http://127.0.0.1:47820',
      toolEndpoint: 'http://127.0.0.1:47820/v1/local/tool'
    })
  })

  it('serves unauthenticated health metadata on loopback', async () => {
    const info = await startLocalAgentServer({ preferredPort: 47821, token: 'test-token' })

    const response = await fetch(`${info.localUrl}/health`)
    const body = await response.json()

    expect(response.status).toBe(200)
    expect(body).toEqual({
      ok: true,
      app: {
        name: 'Omi Windows',
        version: '1.2.3',
        appId: 'com.omiwindows.app'
      },
      localUrl: info.localUrl,
      toolEndpoint: `${info.localUrl}/v1/local/tool`
    })
  })

  it('shares one startup attempt across concurrent callers', async () => {
    const [first, second] = await Promise.all([
      startLocalAgentServer({ preferredPort: 47824, token: 'test-token' }),
      startLocalAgentServer({ preferredPort: 47824, token: 'other-token' })
    ])

    expect(second).toEqual(first)

    await stopLocalAgentServer()
    await expect(fetch(`${first.localUrl}/health`)).rejects.toThrow()
  })

  it('requires bearer auth for local tool discovery and invocation', async () => {
    const info = await startLocalAgentServer({ preferredPort: 47822, token: 'test-token' })

    const missingAuthTools = await fetch(`${info.localUrl}/v1/local/tools`)
    expect(missingAuthTools.status).toBe(401)

    const tools = await fetch(`${info.localUrl}/v1/local/tools`, {
      headers: { authorization: 'Bearer test-token' }
    })
    const toolsBody = await tools.json()
    expect(toolsBody).toMatchObject({
      ok: true,
      toolEndpoint: `${info.localUrl}/v1/local/tool`
    })
    expect(toolsBody.tools.map((tool: { name: string }) => tool.name)).toEqual(
      expect.arrayContaining([
        'get_local_status',
        'execute_sql',
        'search_screen_history',
        'semantic_search',
        'get_screenshot',
        'get_daily_recap',
        'search_tasks',
        'complete_task',
        'delete_task'
      ])
    )

    const missingAuthToolCall = await fetch(`${info.localUrl}/v1/local/tool`, { method: 'POST' })
    expect(missingAuthToolCall.status).toBe(401)

    const toolCall = await fetch(`${info.localUrl}/v1/local/tool`, {
      method: 'POST',
      headers: {
        authorization: 'Bearer test-token',
        'content-type': 'application/json'
      },
      body: JSON.stringify({ name: 'get_local_status', arguments: {} })
    })
    expect(toolCall.status).toBe(200)
    await expect(toolCall.json()).resolves.toMatchObject({
      ok: true,
      name: 'get_local_status',
      result: {
        ok: true,
        mode: 'local_omi_windows'
      }
    })

    const unknownTool = await fetch(`${info.localUrl}/v1/local/tool`, {
      method: 'POST',
      headers: {
        authorization: 'Bearer test-token',
        'content-type': 'application/json'
      },
      body: JSON.stringify({ name: 'noop', arguments: {} })
    })
    expect(unknownTool.status).toBe(404)
    await expect(unknownTool.json()).resolves.toMatchObject({
      ok: false,
      error: { code: 'unknown_tool' }
    })
  })

  it('rejects oversized local tool request bodies', async () => {
    const info = await startLocalAgentServer({ preferredPort: 47825, token: 'test-token' })

    const response = await fetch(`${info.localUrl}/v1/local/tool`, {
      method: 'POST',
      headers: {
        authorization: 'Bearer test-token',
        'content-type': 'application/json'
      },
      body: 'x'.repeat(1_048_577)
    })

    expect(response.status).toBe(413)
    await expect(response.json()).resolves.toMatchObject({
      ok: false,
      error: { code: 'request_body_too_large', max_bytes: 1_048_576 }
    })
  })

  it('returns 400 for malformed request targets instead of throwing', async () => {
    const info = await startLocalAgentServer({ preferredPort: 47826, token: 'test-token' })

    const response = await rawRequest(
      info.port,
      'GET http://[::1/path HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'
    )

    expect(response).toContain('400')
    expect(response).toContain('invalid_request_target')
  })

  it('falls back from the default port without binding to all interfaces', async () => {
    const occupied = createServer((_req, res) => res.end('occupied'))
    await listen(occupied, LOCAL_AGENT_DEFAULT_PORT)

    try {
      const info = await startLocalAgentServer({ token: 'test-token' })

      expect(info).toMatchObject({
        host: '127.0.0.1',
        port: LOCAL_AGENT_DEFAULT_PORT + 1,
        localUrl: `http://127.0.0.1:${LOCAL_AGENT_DEFAULT_PORT + 1}`,
        toolEndpoint: `http://127.0.0.1:${LOCAL_AGENT_DEFAULT_PORT + 1}/v1/local/tool`
      })
    } finally {
      await close(occupied)
    }
  })
})
