// Renderer seam onto the main-process MCP export connectors. The hosted key lives
// in main; here we only relay the Firebase uid (+ token for mutations) and get
// back non-secret connector status. Mirrors lib/byokKeys' trust split.

import { auth } from './firebase'
import type {
  McpConnectorId,
  McpExportsSnapshot,
  McpConnectResult,
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

/** Mint-or-reuse the hosted key and write this connector's MCP config. Returns
 *  the fresh snapshot plus a manual setup card when CLI automation fell back. */
export async function connectMcp(id: McpConnectorId): Promise<McpConnectResult | null> {
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

/** The ChatGPT/Claude assisted-connector cards (static field values). */
export async function getCloudInfo(): Promise<McpCloudConnectorInfo[]> {
  return window.omi.mcpCloudInfo()
}

/** Open a cloud connector's provider connector page. */
export async function openCloudConnector(url: string): Promise<void> {
  return window.omi.mcpOpenCloudConnector(url)
}

// Local "opened" latch for cloud connectors. Mac's connected-detection for
// ChatGPT/Claude is an unclosed gap (no reliable probe), so — matching it — we
// only remember that the user opened the guide, surfaced as "Reconnect". Stored
// in localStorage, which this app clears on sign-out, so it never leaks across
// accounts.
const cloudLatchKey = (id: string): string => `omi.mcpCloud.${id}.openedAt`

export function markCloudConnectorOpened(id: string): void {
  try {
    localStorage.setItem(cloudLatchKey(id), String(Date.now()))
  } catch {
    /* storage unavailable — the latch is a cosmetic hint only */
  }
}

export function isCloudConnectorOpened(id: string): boolean {
  try {
    return !!localStorage.getItem(cloudLatchKey(id))
  } catch {
    return false
  }
}

/** Copy the memory pack to the clipboard and open the provider chat. */
export async function runMemoryPack(
  provider: 'gemini' | 'chatgpt' | 'claude',
  memories: ExportMemory[]
): Promise<string> {
  return window.omi.mcpMemoryPack(provider, memories)
}
