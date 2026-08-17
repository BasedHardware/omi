import { browserApiBase as apiBase } from '@/src/lib/api/browser-base';

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
 * LIVE: POST /v1/mcp/keys. `scopes` is authoritative per key — the route 400s on
 * an unknown or empty scope list, and that detail is surfaced to the user.
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
 * LIVE: POST /v1/mcp/keys/{key_id}/rotate. The new raw key is returned exactly
 * once. There is no grace window — the previous secret stops working at once.
 */
export function rotateMcpKey(token: string, keyId: string) {
  return request<McpApiKeyCreated>(
    `/v1/mcp/keys/${encodeURIComponent(keyId)}/rotate`,
    token,
    { method: 'POST' },
  );
}
