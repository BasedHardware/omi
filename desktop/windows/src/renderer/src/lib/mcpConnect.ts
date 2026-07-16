// Renderer seam onto the main-process MCP export connectors. The hosted key lives
// in main; here we only relay the Firebase uid (+ token for mutations) and get
// back non-secret connector status. Mirrors lib/byokKeys' trust split.

import { auth } from './firebase'
import type {
  McpConnectorId,
  McpExportsSnapshot,
  McpCloudConnectorInfo
} from '../../../shared/mcpExports'
import type { ExportMemory } from '../../../shared/types'

async function creds(): Promise<{ token: string; uid: string } | null> {
  const user = auth.currentUser
  if (!user) return null
  return { token: await user.getIdToken(), uid: user.uid }
}

/** Current connector status for the signed-in account, or null when signed out. */
export async function getMcpStatus(): Promise<McpExportsSnapshot | null> {
  const uid = auth.currentUser?.uid
  if (!uid) return null
  return window.omi.mcpStatus(uid)
}

/** Mint-or-reuse the hosted key and write this connector's MCP config. */
export async function connectMcp(id: McpConnectorId): Promise<McpExportsSnapshot | null> {
  const c = await creds()
  if (!c) return null
  return window.omi.mcpConnect(id, c.token, c.uid)
}

/** Remove this connector's MCP config entry. */
export async function disconnectMcp(id: McpConnectorId): Promise<McpExportsSnapshot | null> {
  const uid = auth.currentUser?.uid
  if (!uid) return null
  return window.omi.mcpDisconnect(id, uid)
}

/** Rotate the hosted key and rewrite any already-connected configs. */
export async function rotateMcpKey(): Promise<McpExportsSnapshot | null> {
  const c = await creds()
  if (!c) return null
  return window.omi.mcpRotateKey(c.token, c.uid)
}

/** The ChatGPT/Claude assisted-connector cards, with connected state resolved. */
export async function getCloudInfo(): Promise<McpCloudConnectorInfo[]> {
  const token = (await auth.currentUser?.getIdToken()) ?? null
  return window.omi.mcpCloudInfo(token)
}

/** Open a cloud connector's provider connector page. */
export async function openCloudConnector(url: string): Promise<void> {
  return window.omi.mcpOpenCloudConnector(url)
}

/** Copy the memory pack to the clipboard and open the provider chat. */
export async function runMemoryPack(
  provider: 'gemini' | 'chatgpt' | 'claude',
  memories: ExportMemory[]
): Promise<string> {
  return window.omi.mcpMemoryPack(provider, memories)
}
