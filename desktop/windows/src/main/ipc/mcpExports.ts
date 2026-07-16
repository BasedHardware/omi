// IPC surface for the "Use omi memory anywhere" MCP export connectors. Follows
// the house invoke-handler pattern (see byok.ts / codingAgent.ts). The hosted key
// store + config writers are main-process only; these handlers are the renderer
// Connections UI's seam onto them.
//
// SECURITY: the hosted MCP key never crosses to the renderer. The renderer relays
// the Firebase token + its uid; main mints/reads the key, writes it into the
// tool's config file itself, and returns only non-secret status. The key is a
// credential — never logged.

import { ipcMain, webContents, clipboard, shell } from 'electron'
import { McpKeyStore } from '../mcp/mcpKeyStore'
import { McpExportsService } from '../mcp/mcpExportsService'
import { buildCloudConnectors, connectedCloudConnectors } from '../mcp/cloudConnectors'
import { buildMemoryPack, memoryPackChatUrl, type MemoryPackProvider } from '../mcp/memoryPack'
import type { ExportMemory } from '../../shared/types'
import type { McpCloudConnectorInfo } from '../../shared/mcpExports'
import {
  detectClaudeCode,
  claudeMcpConnected,
  writeClaudeMcpEntry,
  removeClaudeMcpEntry,
  claudeConfigPath
} from '../mcp/claudeConfig'
import {
  probeCliConnector,
  connectCodex,
  disconnectCodex,
  codexConnected
} from '../mcp/cliConnectors'
import type {
  McpConnectorId,
  McpConnectorStatus,
  McpExportsSnapshot
} from '../../shared/mcpExports'

let service: McpExportsService | null = null

function getService(): McpExportsService {
  if (!service) service = new McpExportsService(new McpKeyStore())
  return service
}

function apiBase(): string {
  return import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me'
}

/** Ping every renderer so the Connections UI re-reads connector status. */
function broadcastChanged(): void {
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('mcp:changed')
  }
}

async function claudeStatus(base: string): Promise<McpConnectorStatus> {
  const connected = claudeMcpConnected(base)
  const detected = detectClaudeCode()
  return {
    id: 'claudeCode',
    kind: connected ? 'connected' : detected ? 'available' : 'requiresTool',
    configPath: claudeConfigPath()
  }
}

async function codexStatus(): Promise<McpConnectorStatus> {
  const probe = probeCliConnector('codex')
  const connected = probe.detected ? await codexConnected() : false
  return {
    id: 'codex',
    kind: connected ? 'connected' : probe.detected && probe.writable ? 'available' : 'requiresTool'
  }
}

function cliOnlyStatus(id: 'openclaw' | 'hermes'): McpConnectorStatus {
  const probe = probeCliConnector(id)
  // OpenClaw/Hermes config-write is not yet ported (needs the exact macOS
  // syntax), so they are never 'available' — a detected-but-unported tool still
  // reports 'requiresTool' rather than offering a Connect action that no-ops.
  return { id, kind: probe.detected && probe.writable ? 'available' : 'requiresTool' }
}

async function snapshot(ownerUserId: string): Promise<McpExportsSnapshot> {
  const base = apiBase()
  const connectors = await Promise.all([
    claudeStatus(base),
    codexStatus(),
    Promise.resolve(cliOnlyStatus('openclaw')),
    Promise.resolve(cliOnlyStatus('hermes'))
  ])
  return { hasKey: getService().hasKey(ownerUserId), connectors }
}

/** Mint-or-reuse the hosted key, then write the connector's config. */
async function connect(
  connectorId: McpConnectorId,
  token: string,
  ownerUserId: string
): Promise<McpExportsSnapshot> {
  const base = apiBase()
  const record = await getService().ensureKey(ownerUserId, token, base)
  if (connectorId === 'claudeCode') {
    writeClaudeMcpEntry(base, record.key)
  } else if (connectorId === 'codex') {
    await connectCodex(base, record.key)
  } else {
    throw new Error(`Connector ${connectorId} is not yet available for connect`)
  }
  broadcastChanged()
  return snapshot(ownerUserId)
}

async function disconnect(
  connectorId: McpConnectorId,
  ownerUserId: string
): Promise<McpExportsSnapshot> {
  if (connectorId === 'claudeCode') removeClaudeMcpEntry()
  else if (connectorId === 'codex') await disconnectCodex()
  broadcastChanged()
  return snapshot(ownerUserId)
}

/** Rotate the hosted key and rewrite any already-connected config connectors. */
async function rotate(token: string, ownerUserId: string): Promise<McpExportsSnapshot> {
  const base = apiBase()
  const record = await getService().rotateKey(ownerUserId, token, base)
  // Re-point every connector that was pointing at the old key.
  if (claudeMcpConnected(base)) writeClaudeMcpEntry(base, record.key)
  if (await codexConnected()) await connectCodex(base, record.key)
  broadcastChanged()
  return snapshot(ownerUserId)
}

/** Cloud (OAuth) connector cards + their connected state (grants lookup). */
async function cloudInfo(token: string | null): Promise<McpCloudConnectorInfo[]> {
  const base = apiBase()
  const infos = buildCloudConnectors(base)
  const connected = await connectedCloudConnectors(base, token)
  return infos.map((info) => ({ ...info, connected: connected.has(info.id) }))
}

/**
 * Build the memory pack for `provider`, copy it to the clipboard, and open the
 * provider's chat. The renderer owns the memories (its API token) and passes them
 * in. Returns the chat URL that was opened.
 */
function openMemoryPack(provider: MemoryPackProvider, memories: ExportMemory[]): string {
  clipboard.writeText(buildMemoryPack(provider, memories))
  const url = memoryPackChatUrl(provider)
  void shell.openExternal(url)
  return url
}

/** Open a cloud connector's provider connector page (the assisted "open & guide"). */
function openCloudConnector(url: string): void {
  void shell.openExternal(url)
}

export function registerMcpExportsHandlers(): void {
  ipcMain.handle('mcp:status', (_e, ownerUserId: string) => snapshot(ownerUserId))
  ipcMain.handle('mcp:cloudInfo', (_e, token: string | null) => cloudInfo(token))
  ipcMain.handle('mcp:openCloudConnector', (_e, url: string) => openCloudConnector(url))
  ipcMain.handle('mcp:memoryPack', (_e, provider: MemoryPackProvider, memories: ExportMemory[]) =>
    openMemoryPack(provider, memories)
  )
  ipcMain.handle(
    'mcp:connect',
    (_e, connectorId: McpConnectorId, token: string, ownerUserId: string) =>
      connect(connectorId, token, ownerUserId)
  )
  ipcMain.handle('mcp:disconnect', (_e, connectorId: McpConnectorId, ownerUserId: string) =>
    disconnect(connectorId, ownerUserId)
  )
  ipcMain.handle('mcp:rotateKey', (_e, token: string, ownerUserId: string) =>
    rotate(token, ownerUserId)
  )
}
