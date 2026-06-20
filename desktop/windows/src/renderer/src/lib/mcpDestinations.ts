export type McpDestinationId = 'chatgpt' | 'claude' | 'claude-code' | 'codex' | 'agents'

export type McpSetup = {
  serverURL: string
  copyTitle?: string
  copyText?: string
  steps: string[]
  openURL?: string
  openTitle?: string
}

export type McpDestination = {
  id: McpDestinationId
  title: string
  subtitle: string
  description: string
  setup: (key: string) => McpSetup
}

export type McpHealthResult = {
  memoryCount: number
}

const DEFAULT_OMI_API_BASE = 'https://api.omi.me'

function normalizedApiBase(): string {
  const raw = (import.meta.env.VITE_OMI_API_BASE as string | undefined) || DEFAULT_OMI_API_BASE
  return raw.endsWith('/') ? raw : `${raw}/`
}

export const mcpBaseURL = normalizedApiBase()
export const mcpServerURL = `${mcpBaseURL}v1/mcp/sse`
export const mcpAuthorizeURL = `${mcpBaseURL}authorize`
export const mcpTokenURL = `${mcpBaseURL}token`

export function buildHostedMcpHealthRequest(key: string): { url: string; init: RequestInit } {
  return {
    url: mcpServerURL,
    init: {
      method: 'POST',
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
    }
  }
}

export function parseHostedMcpMemoryCount(payload: unknown): number {
  const rpc = payload as {
    error?: { message?: unknown }
    result?: { content?: Array<{ text?: unknown }> }
  }
  if (rpc.error) {
    const message = typeof rpc.error.message === 'string' ? rpc.error.message : 'Unknown error'
    throw new Error(`Hosted MCP failed: ${message}`)
  }

  const text = rpc.result?.content?.find((item) => typeof item.text === 'string')?.text
  if (typeof text !== 'string') {
    throw new Error('Hosted MCP did not return memory data.')
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Hosted MCP returned unreadable memory data.')
  }

  const memories = (parsed as { memories?: unknown }).memories
  if (!Array.isArray(memories)) {
    throw new Error('Hosted MCP did not return memory data.')
  }
  return memories.length
}

export async function testHostedMcpConnection(key: string): Promise<McpHealthResult> {
  const { url, init } = buildHostedMcpHealthRequest(key)
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    throw new Error(`Hosted MCP request failed: ${(error as Error).message}`)
  }

  if (!response.ok) {
    throw new Error(`Hosted MCP returned HTTP ${response.status}.`)
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error('Hosted MCP returned invalid JSON.')
  }

  return { memoryCount: parseHostedMcpMemoryCount(payload) }
}

export const mcpDestinations: McpDestination[] = [
  {
    id: 'chatgpt',
    title: 'ChatGPT',
    subtitle: 'Custom connector',
    description: 'Connect Omi Memory so ChatGPT can read your memories live.',
    setup: () => ({
      serverURL: mcpServerURL,
      steps: [
        'Open ChatGPT -> Settings -> Apps -> Advanced, then enable Developer mode.',
        'Create app -> name it "Omi Memory" and paste the server URL below.',
        'Authentication: OAuth. In Advanced OAuth settings set Client ID "omi", Client Secret to your key, and token auth method "client_secret_post".',
        `Auth URL: ${mcpAuthorizeURL} - Token URL: ${mcpTokenURL}`,
        'Create, then Connect. The connector syncs to ChatGPT desktop and mobile.'
      ],
      openURL: 'https://chatgpt.com/',
      openTitle: 'Open ChatGPT'
    })
  },
  {
    id: 'claude',
    title: 'Claude',
    subtitle: 'Custom connector',
    description: 'Connect Omi Memory so Claude can read your memories live.',
    setup: () => ({
      serverURL: mcpServerURL,
      steps: [
        'Open claude.ai -> Settings -> Connectors -> Add custom connector.',
        'Name it "Omi Memory" and paste the server URL below.',
        'Under Advanced settings set OAuth Client ID to "omi" and Client Secret to your key below.',
        'Click Add, then Connect. The connector syncs to Claude desktop and mobile.'
      ],
      openURL: 'https://claude.ai/settings/connectors',
      openTitle: 'Open Claude Connectors'
    })
  },
  {
    id: 'claude-code',
    title: 'Claude Code',
    subtitle: 'Terminal command',
    description: 'Register Omi as a user-scope MCP server for every Claude Code project.',
    setup: (key) => ({
      serverURL: mcpServerURL,
      copyTitle: 'Copy command',
      copyText: `claude mcp add --scope user --transport http omi-memory ${mcpServerURL} --header "Authorization: Bearer ${key}"`,
      steps: [
        'Run the command below in your terminal.',
        'It registers Omi at user scope, so every Claude Code project can read your memories.'
      ]
    })
  },
  {
    id: 'codex',
    title: 'Codex',
    subtitle: 'Config block',
    description: 'Add Omi Memory to Codex as a hosted MCP server.',
    setup: (key) => ({
      serverURL: mcpServerURL,
      copyTitle: 'Copy config',
      copyText: `[mcp_servers.omi-memory]
command = "npx"
args = ["-y", "mcp-remote", "${mcpServerURL}", "--header", "Authorization: Bearer ${key}"]`,
      steps: [
        'Add the block below to ~/.codex/config.toml.',
        'Restart Codex to load Omi memories over MCP.'
      ]
    })
  },
  {
    id: 'agents',
    title: 'AI Agents',
    subtitle: 'Generic MCP setup',
    description: 'Use the server URL and bearer key with any MCP-compatible agent.',
    setup: (key) => ({
      serverURL: mcpServerURL,
      copyTitle: 'Copy JSON',
      copyText: JSON.stringify(
        {
          'omi-memory': {
            transport: 'http',
            url: mcpServerURL,
            headers: { Authorization: `Bearer ${key}` }
          }
        },
        null,
        2
      ),
      steps: [
        'Create a hosted HTTP MCP server entry named "omi-memory".',
        'Use the server URL below and set Authorization to Bearer plus your Omi MCP key.',
        'Test the connection with get_memories and a small limit before relying on it.'
      ]
    })
  }
]
