import { clipboard } from 'electron'
import type { LocalAgentStatus, LocalAgentToolsTestResult } from '../../shared/types'
import { getLocalAgentSettings, setLocalAgentSettings } from './settings'
import { getLocalAgentServerInfo, startLocalAgentServer, stopLocalAgentServer } from './server'
import { ensureLocalAgentToken, loadLocalAgentToken, rotateLocalAgentToken } from './tokenStore'

const LOCAL_AGENT_HOST = '127.0.0.1'
const TOKEN_CLIPBOARD_TTL_MS = 60_000

let tokenClipboardClearTimer: NodeJS.Timeout | null = null

function validatePort(port: number): number {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('Local agent port must be between 1024 and 65535')
  }
  return port
}

function tokenStatusError(): string {
  return 'Local agent token is unavailable. Check secure storage and rotate the token if needed.'
}

export function getLocalAgentStatus(): LocalAgentStatus {
  const settings = getLocalAgentSettings()
  const info = getLocalAgentServerInfo()
  let hasToken = false
  let tokenError: string | null = null
  try {
    hasToken = loadLocalAgentToken() !== null
  } catch (error) {
    console.warn('[local-agent] failed to load token:', error)
    tokenError = tokenStatusError()
  }
  return {
    enabled: settings.enabled,
    running: info !== null,
    host: info?.host ?? LOCAL_AGENT_HOST,
    configuredPort: settings.port,
    currentPort: info?.port ?? null,
    localUrl: info?.localUrl ?? null,
    toolEndpoint: info?.toolEndpoint ?? null,
    hasToken,
    tokenError
  }
}

export async function setLocalAgentEnabled(enabled: boolean): Promise<LocalAgentStatus> {
  const settings = setLocalAgentSettings({ ...getLocalAgentSettings(), enabled })
  if (!enabled) {
    await stopLocalAgentServer()
    return getLocalAgentStatus()
  }

  await startLocalAgentServer({ preferredPort: settings.port })
  return getLocalAgentStatus()
}

export async function setLocalAgentPort(port: number): Promise<LocalAgentStatus> {
  const validatedPort = validatePort(port)
  const settings = setLocalAgentSettings({ ...getLocalAgentSettings(), port: validatedPort })

  if (settings.enabled) {
    await stopLocalAgentServer()
    await startLocalAgentServer({ preferredPort: settings.port })
  }

  return getLocalAgentStatus()
}

export function copyLocalAgentToken(): LocalAgentStatus {
  const token = ensureLocalAgentToken()
  clipboard.writeText(token)
  if (tokenClipboardClearTimer) clearTimeout(tokenClipboardClearTimer)
  tokenClipboardClearTimer = setTimeout(() => {
    if (clipboard.readText() === token) {
      clipboard.writeText('')
    }
    tokenClipboardClearTimer = null
  }, TOKEN_CLIPBOARD_TTL_MS)
  return getLocalAgentStatus()
}

export async function rotateLocalAgentAccessToken(): Promise<LocalAgentStatus> {
  rotateLocalAgentToken()
  const settings = getLocalAgentSettings()

  if (settings.enabled) {
    await stopLocalAgentServer()
    await startLocalAgentServer({ preferredPort: settings.port })
  }

  return getLocalAgentStatus()
}

export async function testLocalAgentTools(): Promise<LocalAgentToolsTestResult> {
  const info = getLocalAgentServerInfo()
  if (!info) {
    return { ok: false, error: 'Local agent API is not listening' }
  }

  try {
    const token = loadLocalAgentToken()
    if (!token) {
      return { ok: false, error: 'Local agent token is missing' }
    }

    const response = await fetch(`${info.localUrl}/v1/local/tools`, {
      headers: { authorization: `Bearer ${token}` }
    })
    if (!response.ok) {
      return { ok: false, status: response.status, error: `HTTP ${response.status}` }
    }

    const body = (await response.json()) as { tools?: unknown[] }
    const toolCount = Array.isArray(body.tools) ? body.tools.length : 0
    return { ok: true, status: response.status, toolCount }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Local agent tools test failed'
    }
  }
}
