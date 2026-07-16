// Shared constants + types for the "Use omi memory anywhere" MCP memory-bank
// exports. Pure, browser-safe module: no Node built-ins, no Electron, no I/O —
// imported by BOTH the main process (config writers, mint client) and the
// renderer (connector UI). All wire values live here so the config a tool reads
// and the copy the UI shows can never drift apart.
//
// Mirrors macOS's memory-export MCP flow: a hosted MCP key authenticates the
// external tool against Omi's hosted MCP SSE endpoint, and each config-write
// agent (Claude Code, Codex, OpenClaw, Hermes) points its MCP client there.

/** The MCP server entry key every config writer uses (Mac parity). */
export const MCP_SERVER_KEY = 'omi-memory'

/** Display name the hosted MCP key is minted under. */
export const MCP_KEY_NAME = 'Omi Desktop'

/** Path of Omi's hosted MCP SSE endpoint, appended to the API base. */
export const MCP_SSE_PATH = '/v1/mcp/sse'

/** Path of the hosted MCP key REST collection. */
export const MCP_KEYS_PATH = '/v1/mcp/keys'

/** Build the hosted MCP SSE URL an external tool connects to. */
export function mcpServerUrl(apiBase: string): string {
  return `${apiBase.replace(/\/+$/, '')}${MCP_SSE_PATH}`
}

/**
 * The `mcpServers["omi-memory"]` entry written into an HTTP-transport MCP client
 * config (Claude Code's ~/.claude.json). `type: "http"` is Omi's hosted SSE
 * transport; the hosted key rides as a Bearer header.
 */
export interface McpHttpServerEntry {
  type: 'http'
  url: string
  headers: { Authorization: string }
}

export function buildHttpServerEntry(url: string, key: string): McpHttpServerEntry {
  return { type: 'http', url, headers: { Authorization: `Bearer ${key}` } }
}

// --- Connector taxonomy -----------------------------------------------------
// The non-"Ask Omi" rows of the export column. Two kinds:
//   • 'config' — Omi writes the tool's MCP client config for it (needs a hosted
//     key). Claude Code ships now; codex/openclaw/hermes are gated behind a CLI
//     presence check (a "requires <tool>" row when the CLI/config is absent).
//   • 'cloud'  — a hosted OAuth connector (ChatGPT/Claude). No hosted key; an
//     assisted "open & guide" flow shows copy-rows for the provider's form.

export type McpConnectorId = 'claudeCode' | 'codex' | 'openclaw' | 'hermes'

export interface McpConfigConnector {
  id: McpConnectorId
  /** Row title in the exports list. */
  title: string
  /** Brand mark key (ConnectorBrandMark). */
  brand: 'claude' | 'chatgpt' | 'openclaw' | 'hermes'
  /** The user-facing tool name shown in the "requires <tool>" gated state. */
  tool: string
  /** True for Claude Code — always available (pure JSON write, no CLI needed). */
  alwaysAvailable: boolean
}

export const MCP_CONFIG_CONNECTORS: readonly McpConfigConnector[] = [
  {
    id: 'claudeCode',
    title: 'Claude / Claude Code',
    brand: 'claude',
    tool: 'Claude Code',
    alwaysAvailable: true
  },
  { id: 'codex', title: 'ChatGPT / Codex', brand: 'chatgpt', tool: 'Codex', alwaysAvailable: false },
  { id: 'openclaw', title: 'OpenClaw', brand: 'openclaw', tool: 'OpenClaw', alwaysAvailable: false },
  { id: 'hermes', title: 'Hermes', brand: 'hermes', tool: 'Hermes', alwaysAvailable: false }
]

/** The per-connector runtime state the UI renders. */
export type McpConnectorStatusKind =
  | 'connected' // MCP entry present in the tool's config
  | 'available' // tool present, not yet connected → offer "Connect"
  | 'requiresTool' // CLI/config not detected → "requires <tool>" (no shell attempt)

export interface McpConnectorStatus {
  id: McpConnectorId
  kind: McpConnectorStatusKind
  /** Where the config lives / would be written (for the connected-state detail). */
  configPath?: string
}
