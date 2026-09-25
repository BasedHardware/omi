// Pure helpers for the hosted MCP surface (Streamable HTTP). Shared by the
// Settings developer section and its tests so the displayed server URL and the
// copied Claude config can never drift apart.

/** Canonical hosted MCP endpoint path appended to the API base. */
export const MCP_ENDPOINT_PATH = '/v1/mcp';

/**
 * Canonical hosted MCP URL derived from `apiBase` (e.g.
 * `NEXT_PUBLIC_API_BASE_URL`), with trailing slashes normalized away.
 */
export function hostedMcpUrl(apiBase: string): string {
  return `${apiBase.replace(/\/+$/, '')}${MCP_ENDPOINT_PATH}`;
}

/**
 * The Claude Code `~/.claude.json` `mcpServers` config JSON for the hosted
 * Streamable HTTP endpoint — `type: "http"` plus a Bearer header, no local
 * transport. The same string is rendered and copied. (Claude Desktop adds
 * remote servers via Settings → Connectors, not a JSON file.)
 */
export function hostedMcpConfigJson(mcpUrl: string): string {
  return `{
  "mcpServers": {
    "omi": {
      "type": "http",
      "url": ${JSON.stringify(mcpUrl)},
      "headers": {
        "Authorization": "Bearer <key>"
      }
    }
  }
}`;
}
