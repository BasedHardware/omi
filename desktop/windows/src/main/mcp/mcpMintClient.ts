// Hosted MCP key REST client (main process). Mints / lists / revokes the hosted
// MCP API key against Omi's backend. The Firebase bearer token is RELAYED from
// the renderer (same pattern as byok:enroll / the listen WebSocket) since the
// session lives in the renderer's Firebase client — main never holds it.
//
// Endpoints (see backend routers/mcp.py):
//   POST   /v1/mcp/keys      { name } → { id, name, key }   (raw key returned ONCE)
//   GET    /v1/mcp/keys      → { keys: [{ id, name, ... }] } | [{ id, name }]
//   DELETE /v1/mcp/keys/{id} → 200/204
//
// The minted `key` is a credential: it is returned to the caller (who encrypts it
// at rest) and NEVER logged here.

import { MCP_KEYS_PATH, MCP_KEY_NAME } from '../../shared/mcpExports'

/** A freshly minted key — the only time the raw `key` is available. */
export interface MintedMcpKey {
  id: string
  name: string
  key: string
}

/** Key metadata as listed by the backend (never includes the secret). */
export interface McpKeyInfo {
  id: string
  name: string
}

/** Injectable fetch so tests can mock the network. Defaults to global fetch. */
export type FetchLike = typeof fetch

function base(apiBase: string): string {
  return `${apiBase.replace(/\/+$/, '')}${MCP_KEYS_PATH}`
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

async function asError(res: Response, verb: string): Promise<Error> {
  // Read a short body for context but never echo secrets — these are key-mgmt
  // endpoints whose error bodies are backend messages, not key material.
  let detail = ''
  try {
    detail = (await res.text()).slice(0, 200)
  } catch {
    /* ignore */
  }
  return new Error(`MCP key ${verb} failed (${res.status})${detail ? `: ${detail}` : ''}`)
}

/** Mint a new hosted MCP key. Returns the raw key (available only here, once). */
export async function mintMcpKey(
  apiBase: string,
  token: string,
  name: string = MCP_KEY_NAME,
  fetchImpl: FetchLike = fetch
): Promise<MintedMcpKey> {
  const res = await fetchImpl(base(apiBase), {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ name })
  })
  if (!res.ok) throw await asError(res, 'mint')
  const data = (await res.json()) as Partial<MintedMcpKey>
  if (!data.id || !data.key) throw new Error('MCP key mint returned no key')
  return { id: data.id, name: data.name ?? name, key: data.key }
}

/** List existing hosted MCP keys (metadata only). Tolerates array or {keys:[…]}. */
export async function listMcpKeys(
  apiBase: string,
  token: string,
  fetchImpl: FetchLike = fetch
): Promise<McpKeyInfo[]> {
  const res = await fetchImpl(base(apiBase), { method: 'GET', headers: authHeaders(token) })
  if (!res.ok) throw await asError(res, 'list')
  const data = (await res.json()) as unknown
  const rows = Array.isArray(data)
    ? data
    : Array.isArray((data as { keys?: unknown[] })?.keys)
      ? (data as { keys: unknown[] }).keys
      : []
  return rows
    .map((r) => r as Partial<McpKeyInfo>)
    .filter((r): r is McpKeyInfo => typeof r.id === 'string')
    .map((r) => ({ id: r.id, name: r.name ?? '' }))
}

/**
 * List the user's granted MCP OAuth clients (GET /v1/mcp/oauth/grants). Used to
 * detect whether a cloud connector (ChatGPT/Claude) has completed its OAuth
 * handshake — a grant whose client_id matches the connector means "connected".
 * Returns the set of granted client_ids; empty on any error (treated as none).
 */
export async function listOauthGrantClientIds(
  apiBase: string,
  token: string,
  fetchImpl: FetchLike = fetch
): Promise<Set<string>> {
  try {
    const url = `${apiBase.replace(/\/+$/, '')}/v1/mcp/oauth/grants`
    const res = await fetchImpl(url, { method: 'GET', headers: authHeaders(token) })
    if (!res.ok) return new Set()
    const data = (await res.json()) as unknown
    const rows = Array.isArray(data)
      ? data
      : Array.isArray((data as { grants?: unknown[] })?.grants)
        ? (data as { grants: unknown[] }).grants
        : []
    const ids = new Set<string>()
    for (const r of rows) {
      const cid =
        (r as { client_id?: unknown; clientId?: unknown })?.client_id ??
        (r as { clientId?: unknown })?.clientId
      if (typeof cid === 'string') ids.add(cid)
    }
    return ids
  } catch {
    return new Set()
  }
}

/** Revoke a hosted MCP key by id. A 404 is treated as already-gone (idempotent). */
export async function deleteMcpKey(
  apiBase: string,
  token: string,
  id: string,
  fetchImpl: FetchLike = fetch
): Promise<void> {
  const res = await fetchImpl(`${base(apiBase)}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(token)
  })
  if (!res.ok && res.status !== 404) throw await asError(res, 'delete')
}
