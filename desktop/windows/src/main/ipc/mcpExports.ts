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
import { buildCloudConnectors } from '../mcp/cloudConnectors'
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
  connectCli,
  disconnectCli,
  cliConnected,
  buildSetupCard,
  type CliConnectorId
} from '../mcp/cliConnectors'
import type {
  McpConnectorId,
  McpConnectorStatus,
  McpConnectResult,
  McpExportsSnapshot
} from '../../shared/mcpExports'

const CLI_IDS: readonly CliConnectorId[] = ['codex', 'openclaw', 'hermes']

function isCliConnector(id: McpConnectorId): id is CliConnectorId {
  return (CLI_IDS as readonly string[]).includes(id)
}

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

// The current account's stored key (for the key-aware "connected" re-scan). No
// network — null until the account has minted one via a connect.
function storedKey(ownerUserId: string): string | undefined {
  return getService().storedKey(ownerUserId)?.key ?? undefined
}

function claudeStatus(base: string, key: string | undefined): McpConnectorStatus {
  const connected = claudeMcpConnected(base, claudeConfigPath(), key)
  const detected = detectClaudeCode()
  return {
    id: 'claudeCode',
    kind: connected ? 'connected' : detected ? 'available' : 'requiresTool',
    configPath: claudeConfigPath()
  }
}

function cliStatus(id: CliConnectorId, base: string, key: string | undefined): McpConnectorStatus {
  const probe = probeCliConnector(id)
  if (!probe.detected) return { id, kind: 'requiresTool' }
  const connected = key ? cliConnected(id, base, key) : false
  return { id, kind: connected ? 'connected' : 'available' }
}

function snapshot(ownerUserId: string): McpExportsSnapshot {
  const base = apiBase()
  const key = storedKey(ownerUserId)
  return {
    hasKey: getService().hasKey(ownerUserId),
    connectors: [
      claudeStatus(base, key),
      cliStatus('codex', base, key),
      cliStatus('openclaw', base, key),
      cliStatus('hermes', base, key)
    ]
  }
}

/**
 * Mint-or-reuse the hosted key, then write the connector's config. For a CLI
 * connector whose automation FAILS, return its manual setup card so the UI can
 * show the copy-command fallback (Mac's manual path).
 */
async function connect(
  connectorId: McpConnectorId,
  token: string,
  ownerUserId: string
): Promise<McpConnectResult> {
  const base = apiBase()
  const record = await getService().ensureKey(ownerUserId, token, base)
  if (connectorId === 'claudeCode') {
    writeClaudeMcpEntry(base, record.key)
  } else if (isCliConnector(connectorId)) {
    try {
      await connectCli(connectorId, base, record.key)
    } catch {
      // Automation failed (tool quirk / permissions) — fall back to the manual card.
      broadcastChanged()
      return {
        snapshot: snapshot(ownerUserId),
        setupCard: buildSetupCard(connectorId, base, record.key)
      }
    }
  } else {
    throw new Error(`Unknown connector ${connectorId}`)
  }
  broadcastChanged()
  return { snapshot: snapshot(ownerUserId) }
}

async function disconnect(
  connectorId: McpConnectorId,
  ownerUserId: string
): Promise<McpExportsSnapshot> {
  if (connectorId === 'claudeCode') removeClaudeMcpEntry()
  else if (isCliConnector(connectorId)) await disconnectCli(connectorId)
  broadcastChanged()
  return snapshot(ownerUserId)
}

/** Rotate the hosted key and rewrite any already-connected config connectors. */
async function rotate(token: string, ownerUserId: string): Promise<McpExportsSnapshot> {
  const base = apiBase()
  const oldKey = storedKey(ownerUserId)
  // Which connectors were pointing at the OLD key (rewrite only those).
  const claudeWas = claudeMcpConnected(base, claudeConfigPath(), oldKey)
  const cliWas = CLI_IDS.filter((id) => (oldKey ? cliConnected(id, base, oldKey) : false))
  const record = await getService().rotateKey(ownerUserId, token, base)
  if (claudeWas) writeClaudeMcpEntry(base, record.key)
  for (const id of cliWas) {
    try {
      await connectCli(id, base, record.key)
    } catch {
      /* best-effort re-point; the manual card still reflects the new key */
    }
  }
  broadcastChanged()
  return snapshot(ownerUserId)
}

/** Cloud (OAuth) connector cards — static field values. Connected-state is a
 *  local renderer latch (Mac has no reliable probe; we replicate that gap). */
function cloudInfo(): McpCloudConnectorInfo[] {
  return buildCloudConnectors(apiBase())
}

/**
 * Build the memory pack for `provider`, copy it to the clipboard, and open the
 * provider's chat. The renderer owns the memories (its API token) and passes them
 * in. Returns the chat URL that was opened.
 */
function openMemoryPack(provider: MemoryPackProvider, memories: ExportMemory[]): string {
  clipboard.writeText(buildMemoryPack(provider, memories))
  const url = memoryPackChatUrl(provider)
  // Don't spawn a real browser under E2E (keeps the screenshot harness hermetic).
  if (!process.env.OMI_E2E) void shell.openExternal(url)
  return url
}

/** Open a cloud connector's provider connector page (the assisted "open & guide"). */
function openCloudConnector(url: string): void {
  if (!process.env.OMI_E2E) void shell.openExternal(url)
}

export function registerMcpExportsHandlers(): void {
  ipcMain.handle('mcp:status', (_e, ownerUserId: string) => snapshot(ownerUserId))
  ipcMain.handle('mcp:cloudInfo', () => cloudInfo())
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
