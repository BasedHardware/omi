import { createServer } from 'http'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const electronState = vi.hoisted(() => ({
  userData: '',
  encryptionAvailable: true,
  clipboardText: ''
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
  clipboard: {
    writeText: (value: string): void => {
      electronState.clipboardText = value
    }
  },
  safeStorage: {
    isEncryptionAvailable: (): boolean => electronState.encryptionAvailable,
    encryptString: (value: string): Buffer => Buffer.from(`encrypted:${value}`, 'utf8'),
    decryptString: (value: Buffer): string => value.toString('utf8').replace(/^encrypted:/, '')
  }
}))

import {
  buildOmiAgentSetupPrompt,
  copyLocalAgentSetupPrompt,
  copyLocalAgentToken,
  getLocalAgentStatus,
  rotateLocalAgentAccessToken,
  setLocalAgentEnabled,
  setLocalAgentPort,
  testLocalAgentTools
} from './control'
import { stopLocalAgentServer } from './server'
import { loadLocalAgentToken } from './tokenStore'
import { LOCAL_AGENT_DEFAULT_PORT } from './settings'

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('could not allocate port')))
        return
      }
      server.close((error) => {
        if (error) reject(error)
        else resolve(address.port)
      })
    })
  })
}

async function twoFreePorts(): Promise<[number, number]> {
  const first = await freePort()
  let second = await freePort()
  while (second === first) {
    second = await freePort()
  }
  return [first, second]
}

async function fetchTools(localUrl: string, token: string): Promise<Response> {
  return fetch(`${localUrl}/v1/local/tools`, {
    headers: { authorization: `Bearer ${token}` }
  })
}

describe('local agent controls', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-local-agent-control-'))
    electronState.encryptionAvailable = true
    electronState.clipboardText = ''
  })

  afterEach(async () => {
    await stopLocalAgentServer()
    rmSync(electronState.userData, { recursive: true, force: true })
  })

  it('is disabled by default and does not expose a token in status', () => {
    expect(getLocalAgentStatus()).toEqual({
      enabled: false,
      running: false,
      host: '127.0.0.1',
      configuredPort: LOCAL_AGENT_DEFAULT_PORT,
      currentPort: null,
      localUrl: null,
      toolEndpoint: null,
      hasToken: false
    })
  })

  it('enables and disables the loopback server from settings', async () => {
    const port = await freePort()
    await setLocalAgentPort(port)

    const enabled = await setLocalAgentEnabled(true)
    expect(enabled).toMatchObject({
      enabled: true,
      running: true,
      host: '127.0.0.1',
      configuredPort: port,
      currentPort: port,
      localUrl: `http://127.0.0.1:${port}`
    })

    await expect(fetch(`${enabled.localUrl}/health`)).resolves.toMatchObject({ status: 200 })

    const disabled = await setLocalAgentEnabled(false)
    expect(disabled).toMatchObject({
      enabled: false,
      running: false,
      configuredPort: port,
      currentPort: null,
      localUrl: null
    })
    await expect(fetch(`${enabled.localUrl}/health`)).rejects.toThrow()
  })

  it('restarts on a saved port change while enabled', async () => {
    const [firstPort, secondPort] = await twoFreePorts()
    await setLocalAgentPort(firstPort)
    const first = await setLocalAgentEnabled(true)

    const second = await setLocalAgentPort(secondPort)

    expect(second).toMatchObject({
      enabled: true,
      running: true,
      configuredPort: secondPort,
      currentPort: secondPort,
      localUrl: `http://127.0.0.1:${secondPort}`
    })
    await expect(fetch(`${first.localUrl}/health`)).rejects.toThrow()
    await expect(fetch(`${second.localUrl}/health`)).resolves.toMatchObject({ status: 200 })
  })

  it('copies the bearer token without returning it in status', () => {
    const status = copyLocalAgentToken()

    expect(electronState.clipboardText).toMatch(/^[A-Za-z0-9_-]+$/)
    expect(status.hasToken).toBe(true)
    expect(status).not.toHaveProperty('token')
  })

  it('builds an agent setup prompt with hosted and local credentials', () => {
    const prompt = buildOmiAgentSetupPrompt({
      hostedServerUrl: 'https://api.omi.me/v1/mcp/sse',
      hostedKey: 'hosted_secret',
      localUrl: 'http://127.0.0.1:47778',
      localToolEndpoint: 'http://127.0.0.1:47778/v1/local/tool',
      localToken: 'local_secret'
    })

    expect(prompt).toContain('Authorization: Bearer hosted_secret')
    expect(prompt).toContain('Authorization: Bearer local_secret')
    expect(prompt).toContain('GET http://127.0.0.1:47778/v1/local/tools')
    expect(prompt).toContain('same-Windows-PC context')
    expect(prompt).toContain(
      'Do not create, edit, complete, or delete Omi memories or local tasks unless the user clearly asked for that change.'
    )
  })

  it('copies the agent setup prompt from main while enabling the local API', async () => {
    const port = await freePort()
    await setLocalAgentPort(port)

    const status = await copyLocalAgentSetupPrompt({
      hostedServerUrl: 'https://api.omi.me/v1/mcp/sse',
      hostedKey: 'hosted_secret'
    })
    const token = loadLocalAgentToken()
    if (!token || !status.localUrl) throw new Error('expected local agent setup')

    expect(status).toMatchObject({
      enabled: true,
      running: true,
      configuredPort: port,
      currentPort: port,
      localUrl: `http://127.0.0.1:${port}`,
      hasToken: true
    })
    expect(status).not.toHaveProperty('token')
    expect(electronState.clipboardText).toContain('Authorization: Bearer hosted_secret')
    expect(electronState.clipboardText).toContain(`Local Omi Windows URL:\n${status.localUrl}`)
    expect(electronState.clipboardText).toContain(`Authorization: Bearer ${token}`)
    await expect(fetchTools(status.localUrl, token)).resolves.toMatchObject({ status: 200 })
  })

  it('rotates the bearer token and invalidates the old one', async () => {
    const port = await freePort()
    await setLocalAgentPort(port)
    const started = await setLocalAgentEnabled(true)
    const oldToken = loadLocalAgentToken()
    if (!oldToken || !started.localUrl) throw new Error('expected started local agent')

    await expect(fetchTools(started.localUrl, oldToken)).resolves.toMatchObject({ status: 200 })

    const rotated = await rotateLocalAgentAccessToken()
    const newToken = loadLocalAgentToken()
    if (!newToken || !rotated.localUrl) throw new Error('expected rotated local agent')

    expect(newToken).not.toBe(oldToken)
    await expect(fetchTools(rotated.localUrl, oldToken)).resolves.toMatchObject({ status: 401 })
    await expect(fetchTools(rotated.localUrl, newToken)).resolves.toMatchObject({ status: 200 })
  })

  it('tests the authenticated local tools endpoint', async () => {
    await expect(testLocalAgentTools()).resolves.toMatchObject({
      ok: false,
      error: 'Local agent API is not listening'
    })

    await setLocalAgentPort(await freePort())
    await setLocalAgentEnabled(true)

    await expect(testLocalAgentTools()).resolves.toMatchObject({
      ok: true,
      status: 200
    })
  })
})
