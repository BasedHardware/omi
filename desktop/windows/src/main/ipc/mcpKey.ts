import { BrowserWindow, clipboard, dialog, ipcMain, type IpcMainInvokeEvent } from 'electron'
import type {
  McpKeyCopyRequest,
  McpKeyCopyResult,
  McpKeyMetadata,
  McpKeyRecord,
  McpKeyTestResult
} from '../../shared/types'
import { clearMcpKey, loadMcpKey, saveMcpKey } from '../integrations/mcpKeyStore'

const MCP_KEY_PLACEHOLDER = 'YOUR_OMI_MCP_KEY'
const DEFAULT_OMI_API_BASE = 'https://api.omi.me'
const HOSTED_MCP_TIMEOUT_MS = 15_000
const MCP_KEY_CLIPBOARD_CLEAR_MS = 60_000
const MCP_KEY_NAME = 'Omi Windows'

let clipboardClearTimer: NodeJS.Timeout | null = null

function scheduleClipboardClear(copiedText: string): void {
  if (clipboardClearTimer) clearTimeout(clipboardClearTimer)
  clipboardClearTimer = setTimeout(() => {
    clipboardClearTimer = null
    if (clipboard.readText() === copiedText) clipboard.clear()
  }, MCP_KEY_CLIPBOARD_CLEAR_MS)
  clipboardClearTimer.unref?.()
}

function assertTrustedSender(event: IpcMainInvokeEvent): void {
  const url = event.senderFrame?.url ?? ''
  if (
    url.startsWith('file://') ||
    url.startsWith('http://localhost:') ||
    url.startsWith('http://127.0.0.1:') ||
    (process.env.ELECTRON_RENDERER_URL && url.startsWith(process.env.ELECTRON_RENDERER_URL))
  ) {
    return
  }
  throw new Error('MCP key IPC is not available from this renderer')
}

function maskMcpKey(key: string): string {
  if (key.length <= 10) return '********'
  return `${key.slice(0, 6)}********${key.slice(-4)}`
}

function metadataFor(record: McpKeyRecord): McpKeyMetadata {
  return { id: record.id, name: record.name, maskedKey: maskMcpKey(record.key) }
}

function loadRequiredMcpKey(): McpKeyRecord {
  const record = loadMcpKey()
  if (!record) throw new Error('Generate an MCP key first')
  return record
}

function normalizeCopyRequest(value: unknown): McpKeyCopyRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid MCP key copy request')
  }
  const request = value as Partial<McpKeyCopyRequest>
  if (request.kind === 'key') return { kind: 'key' }
  if (request.kind === 'text' && typeof request.text === 'string') {
    return { kind: 'text', text: request.text }
  }
  throw new Error('Invalid MCP key copy request')
}

async function confirmMcpKeyCopy(
  event: IpcMainInvokeEvent,
  request: McpKeyCopyRequest
): Promise<boolean> {
  const parent = BrowserWindow.fromWebContents(event.sender)
  const label = request.kind === 'key' ? 'raw MCP key' : 'setup text containing your MCP key'
  const options = {
    type: 'warning' as const,
    buttons: ['Copy', 'Cancel'],
    defaultId: 1,
    cancelId: 1,
    title: 'Copy MCP key?',
    message: `Copy ${label} to the clipboard?`,
    detail:
      'Anything on your clipboard may be readable by other apps. The clipboard is cleared automatically after 60 seconds. Only copy this when you are ready to paste it into a trusted destination.'
  }
  const choice = parent
    ? await dialog.showMessageBox(parent, options)
    : await dialog.showMessageBox(options)
  return choice.response === 0
}

function mcpBaseURL(): string {
  const raw = process.env.OMI_API_BASE || DEFAULT_OMI_API_BASE
  return raw.endsWith('/') ? raw : `${raw}/`
}

function parseHostedMcpMemoryCount(payload: unknown): number {
  const rpc = payload as {
    error?: { message?: unknown }
    result?: { content?: Array<{ text?: unknown }> }
  }
  if (rpc.error) {
    const message = typeof rpc.error.message === 'string' ? rpc.error.message : 'Unknown error'
    throw new Error(`Hosted MCP failed: ${message}`)
  }
  const text = rpc.result?.content?.find((item) => typeof item.text === 'string')?.text
  if (typeof text !== 'string') throw new Error('Hosted MCP did not return memory data.')
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Hosted MCP returned unreadable memory data.')
  }
  const memories = (parsed as { memories?: unknown }).memories
  if (!Array.isArray(memories)) throw new Error('Hosted MCP did not return memory data.')
  return memories.length
}

function parseCreatedMcpKey(payload: unknown): McpKeyRecord {
  const record = payload as Partial<McpKeyRecord> | null
  if (
    !record ||
    typeof record !== 'object' ||
    typeof record.id !== 'string' ||
    record.id.length === 0 ||
    typeof record.name !== 'string' ||
    record.name.length === 0 ||
    typeof record.key !== 'string' ||
    record.key.length === 0
  ) {
    throw new Error('MCP key creation returned an invalid key record.')
  }
  return { id: record.id, name: record.name, key: record.key }
}

// Create a hosted MCP key against the Omi API and persist it — entirely in the
// main process. The renderer only supplies the Firebase ID token and only ever
// receives masked metadata back; the raw bearer key never crosses IPC toward
// renderer code (the confirmed mcpKey:copy path is the sole way it leaves main).
// Deliberately no retries: POST /v1/mcp/keys is non-idempotent.
async function createAndStoreMcpKey(token: string): Promise<McpKeyMetadata> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), HOSTED_MCP_TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(`${mcpBaseURL()}v1/mcp/keys`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ name: MCP_KEY_NAME })
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('MCP key creation timed out.')
    }
    throw new Error(`MCP key creation failed: ${(error as Error).message}`)
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) throw new Error(`MCP key creation returned HTTP ${response.status}.`)
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error('MCP key creation returned invalid JSON.')
  }
  const record = parseCreatedMcpKey(payload)
  saveMcpKey(record)
  return metadataFor(record)
}

async function testHostedMcpConnection(key: string): Promise<McpKeyTestResult> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), HOSTED_MCP_TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(`${mcpBaseURL()}v1/mcp/sse`, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${key}`
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: {
          name: 'get_memories',
          arguments: { limit: 5 }
        }
      })
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Hosted MCP request timed out.')
    }
    throw new Error(`Hosted MCP request failed: ${(error as Error).message}`)
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) throw new Error(`Hosted MCP returned HTTP ${response.status}.`)
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error('Hosted MCP returned invalid JSON.')
  }
  return { memoryCount: parseHostedMcpMemoryCount(payload) }
}

export function registerMcpKeyHandlers(): void {
  ipcMain.handle(
    'mcpKey:createAndStore',
    async (event, token: unknown): Promise<McpKeyMetadata> => {
      assertTrustedSender(event)
      if (typeof token !== 'string' || token.length === 0) {
        throw new Error('Invalid auth token for MCP key creation')
      }
      return createAndStoreMcpKey(token)
    }
  )

  ipcMain.handle('mcpKey:read', async (event): Promise<McpKeyMetadata | null> => {
    assertTrustedSender(event)
    const record = loadMcpKey()
    return record ? metadataFor(record) : null
  })

  ipcMain.handle('mcpKey:copy', async (event, rawRequest: unknown): Promise<McpKeyCopyResult> => {
    assertTrustedSender(event)
    const record = loadRequiredMcpKey()
    const request = normalizeCopyRequest(rawRequest)
    if (!(await confirmMcpKeyCopy(event, request))) return { copied: false, canceled: true }
    const text =
      request.kind === 'key' ? record.key : request.text.replaceAll(MCP_KEY_PLACEHOLDER, record.key)
    clipboard.writeText(text)
    scheduleClipboardClear(text)
    return { copied: true }
  })

  ipcMain.handle('mcpKey:test', async (event): Promise<McpKeyTestResult> => {
    assertTrustedSender(event)
    return testHostedMcpConnection(loadRequiredMcpKey().key)
  })

  ipcMain.handle('mcpKey:delete', async (event): Promise<void> => {
    assertTrustedSender(event)
    clearMcpKey()
  })
}
