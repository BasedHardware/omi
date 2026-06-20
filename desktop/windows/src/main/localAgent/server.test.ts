import { createServer, type Server } from 'http'
import { mkdtempSync, rmSync } from 'fs'
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
