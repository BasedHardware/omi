// Shared "is this owned MCP entry connected?" parsing: the endpoint comes from
// the entry's declared `url` scalar or the arg right after `mcp-remote`, and the
// Bearer from its Authorization header or `--header` args — never from a URL
// substring floating in arbitrary record text. Imported by both the CLI-connector
// detector and the Claude Code config reader.

/** How an owned config entry relates to the canonical endpoint + key. */
export type EntryConnection = 'connected' | 'needsUpdate' | 'disconnected'

/** Declared endpoint + Bearer parsed out of an owned entry's OWN fields.
 *  `null` marks a field that is present but unparseable, so it counts as
 *  ambiguity, never as absence. */
export interface OwnedEntryScan {
  endpoints: (string | null)[]
  bearers: (string | null)[]
}

/** 'connected' only for the canonical URL + the CURRENT Bearer; the /sse alias
 *  with the same Bearer is 'needsUpdate'. Conflicting declared endpoints or
 *  bearer values are ambiguous → disconnected, never a guess. Omit `key` to
 *  test only that an entry sits on a known endpoint (rewrite-on-rotate). */
export function entryConnection(
  scan: OwnedEntryScan,
  url: string,
  legacyUrl: string,
  key?: string
): EntryConnection {
  const endpoints = new Set(scan.endpoints)
  const endpoint = endpoints.size === 1 ? [...endpoints][0] : null
  if (endpoint === null || endpoint === undefined) return 'disconnected'
  if (key !== undefined) {
    const bearers = new Set(scan.bearers)
    if (bearers.size !== 1 || [...bearers][0] !== key) return 'disconnected'
  }
  if (endpoint === url) return 'connected'
  if (endpoint === legacyUrl) return 'needsUpdate'
  return 'disconnected'
}

/** A JSON-compatible inline string array (what our writers emit for `args`). */
export function stringArrayValue(raw: string): string[] | null {
  const t = raw.trim()
  if (!t.startsWith('[')) return null
  try {
    const v: unknown = JSON.parse(t)
    return Array.isArray(v) && v.every((x) => typeof x === 'string') ? v : null
  } catch {
    return null
  }
}

/** The endpoints a bridge args array declares: every element right after an
 *  `mcp-remote` token. A trailing `mcp-remote` with no URL is ambiguous (null);
 *  multiple occurrences each contribute (conflicts refuse). */
export function argsEndpoint(args: string[]): (string | null)[] {
  const out: (string | null)[] = []
  for (let i = 0; i < args.length; i++) {
    if (args[i] === 'mcp-remote') {
      out.push(typeof args[i + 1] === 'string' ? args[i + 1] : null)
    }
  }
  return out
}

/** `Bearer <token>` from an Authorization header value; anything else (Basic,
 *  empty) is a present-but-unusable credential → null marker. */
export function bearerToken(value: string): string | null {
  const m = value.trim().match(/^Bearer\s+(\S+)$/i)
  return m ? m[1] : null
}

/** Bearer tokens from `Authorization: Bearer x` arg elements (`--header` args). */
export function argsBearerScans(args: string[]): (string | null)[] {
  const out: (string | null)[] = []
  for (const a of args) {
    const m = a.match(/^\s*Authorization\s*:\s*(.+)$/)
    if (m) out.push(bearerToken(m[1]))
  }
  return out
}

/** Parse a JSON server entry (OpenClaw mcp.servers / Claude mcpServers):
 *  `url`, `args` (mcp-remote bridge), and `headers.Authorization`. An `args`
 *  key that is present but not a string array marks ambiguity, never absence. */
export function jsonEntryScan(server: unknown): OwnedEntryScan {
  const endpoints: (string | null)[] = []
  const bearers: (string | null)[] = []
  if (!server || typeof server !== 'object' || Array.isArray(server)) {
    return { endpoints, bearers }
  }
  const s = server as Record<string, unknown>
  if ('url' in s) endpoints.push(typeof s.url === 'string' ? s.url : null)
  if ('args' in s) {
    const args =
      Array.isArray(s.args) && s.args.every((x): x is string => typeof x === 'string')
        ? s.args
        : null
    if (args) {
      endpoints.push(...argsEndpoint(args))
      bearers.push(...argsBearerScans(args))
    } else {
      endpoints.push(null)
    }
  }
  const headers = s.headers
  if (headers && typeof headers === 'object' && 'Authorization' in headers) {
    const v = (headers as Record<string, unknown>).Authorization
    bearers.push(typeof v === 'string' ? bearerToken(v) : null)
  }
  return { endpoints, bearers }
}
