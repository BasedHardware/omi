// Cloud (OAuth) MCP connectors — ChatGPT and Claude. These connect to Omi's
// hosted MCP endpoint through the PROVIDER's own OAuth flow against Omi's public
// PKCE OAuth clients; they need NO hosted key (secret is left blank). Omi can't
// drive the provider's form, so the assisted flow opens the provider's connector
// page and shows a guide card of copy-rows the user pastes in.
//
// Every value here is ported verbatim from macOS MemoryExportService.swift
// (cloudOAuthClientID / cloudTokenAuthMethod / mcpAuthorizeURL / mcpTokenURL /
// the mcpSetup steps). The client ids are registered + enforced on prod
// (backend check_mcp_oauth_deploy_contract.py): omi-chatgpt-prod (public PKCE,
// secret rejected → blank, token_auth_method "none") and omi-claude-prod.

import { mcpServerUrl, type McpCloudConnectorInfo } from '../../shared/mcpExports'
import { listOauthGrantClientIds } from './mcpMintClient'

function trimBase(apiBase: string): string {
  return apiBase.replace(/\/+$/, '')
}

/** ChatGPT's OAuth client id — prod on api.omi.me, dev otherwise (Mac parity). */
function chatgptClientId(apiBase: string): string {
  return apiBase.includes('api.omi.me') ? 'omi-chatgpt-prod' : 'omi-chatgpt-dev'
}

const CLAUDE_CLIENT_ID = 'omi-claude-prod'

/** Build the ChatGPT + Claude assisted-connector cards for this API base. */
export function buildCloudConnectors(apiBase: string): McpCloudConnectorInfo[] {
  const base = trimBase(apiBase)
  const serverUrl = mcpServerUrl(base)

  const claude: McpCloudConnectorInfo = {
    id: 'claude',
    title: 'Claude',
    connectorUrl: 'https://claude.ai/customize/connectors?modal=add-custom-connector',
    rows: [
      { label: 'Name', value: 'Omi Memory' },
      { label: 'Server URL', value: serverUrl },
      { label: 'OAuth Client ID', value: CLAUDE_CLIENT_ID },
      { label: 'OAuth Client Secret', value: '', blank: true }
    ]
  }

  const chatgpt: McpCloudConnectorInfo = {
    id: 'chatgpt',
    title: 'ChatGPT',
    connectorUrl: 'https://chatgpt.com/#settings/Connectors',
    rows: [
      { label: 'Name', value: 'Omi Memory' },
      { label: 'Server URL', value: serverUrl },
      { label: 'OAuth Client ID', value: chatgptClientId(base) },
      { label: 'Client Secret', value: '', blank: true },
      { label: 'Token auth method', value: 'none' },
      { label: 'Authorization URL', value: `${base}/authorize` },
      { label: 'Token URL', value: `${base}/token` }
    ]
  }

  return [claude, chatgpt]
}

/** The client id a cloud connector's OAuth grant would carry, for connected-detection. */
export function cloudConnectorClientId(id: 'chatgpt' | 'claude', apiBase: string): string {
  return id === 'claude' ? CLAUDE_CLIENT_ID : chatgptClientId(trimBase(apiBase))
}

/**
 * Return the set of cloud connector ids ('chatgpt'/'claude') that have completed
 * their OAuth grant for this account. Empty when signed out or on any error.
 */
export async function connectedCloudConnectors(
  apiBase: string,
  token: string | null
): Promise<Set<'chatgpt' | 'claude'>> {
  const out = new Set<'chatgpt' | 'claude'>()
  if (!token) return out
  const granted = await listOauthGrantClientIds(trimBase(apiBase), token)
  for (const id of ['chatgpt', 'claude'] as const) {
    if (granted.has(cloudConnectorClientId(id, apiBase))) out.add(id)
  }
  return out
}
