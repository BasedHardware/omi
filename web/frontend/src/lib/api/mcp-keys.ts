import envConfig from '@/src/constants/envConfig';

/**
 * MCP scopes are dot-form on the MCP surface. Developer API keys use colon-form.
 */
export const MCP_SCOPES = [
  'memories.read',
  'memories.write',
  'conversations.read',
  'action_items.read',
  'action_items.write',
  'goals.read',
  'chat.read',
  'screen_activity.read',
  'people.read',
] as const;

export type McpScope = (typeof MCP_SCOPES)[number];

export const DEFAULT_MCP_SCOPES: McpScope[] = ['memories.read'];

export interface McpApiKey {
  id: string;
  name: string;
  key_prefix?: string;
  created_at?: string;
  last_used_at?: string | null;
  scopes?: string[];
}

export interface McpApiKeyCreated extends McpApiKey {
  /** Returned exactly once, at creation. Never persisted by the client. */
  key: string;
}

function apiBase(): string {
  return envConfig.API_URL ?? '';
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** LIVE: GET /v1/mcp/keys */
export function listMcpKeys(token: string) {
  return request<McpApiKey[]>('/v1/mcp/keys', token);
}

/**
 * LIVE for `name`. PENDING for `scopes`: the MCP create endpoint currently
 * ignores per-key scopes; a backend change adds them. Sending the field now is
 * forward-compatible and is dropped by the current server.
 */
export function createMcpKey(token: string, name: string, scopes: McpScope[]) {
  return request<McpApiKeyCreated>('/v1/mcp/keys', token, {
    method: 'POST',
    body: JSON.stringify({ name, scopes }),
  });
}

/** LIVE: DELETE /v1/mcp/keys/{key_id} */
export function revokeMcpKey(token: string, keyId: string) {
  return request<void>(`/v1/mcp/keys/${encodeURIComponent(keyId)}`, token, {
    method: 'DELETE',
  });
}

/**
 * PENDING: the rotation endpoint is being added backend-side this cycle. This is
 * the single client seam — when the route lands, only this function changes.
 */
export function rotateMcpKey(token: string, keyId: string) {
  return request<McpApiKeyCreated>(
    `/v1/mcp/keys/${encodeURIComponent(keyId)}/rotate`,
    token,
    { method: 'POST' },
  );
}
