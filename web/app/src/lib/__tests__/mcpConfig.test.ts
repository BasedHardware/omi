import { describe, expect, it } from 'vitest';
import { MCP_ENDPOINT_PATH, hostedMcpConfigJson, hostedMcpUrl } from '@/lib/mcpConfig';

describe('hostedMcpUrl', () => {
  it('joins the canonical /v1/mcp path onto the API base', () => {
    expect(hostedMcpUrl('https://api.omi.me')).toBe('https://api.omi.me/v1/mcp');
  });

  it('normalizes trailing slashes so the endpoint is joined once', () => {
    expect(hostedMcpUrl('https://api.omi.me/')).toBe('https://api.omi.me/v1/mcp');
    expect(hostedMcpUrl('https://api.omi.me///')).toBe('https://api.omi.me/v1/mcp');
  });

  it('never returns the legacy /v1/mcp/sse alias', () => {
    expect(MCP_ENDPOINT_PATH).toBe('/v1/mcp');
    expect(hostedMcpUrl('https://api.omi.me/')).not.toContain('sse');
  });
});

describe('hostedMcpConfigJson', () => {
  const url = 'https://api.omi.me/v1/mcp';

  it('emits a hosted Streamable HTTP mcpServers entry', () => {
    const parsed = JSON.parse(hostedMcpConfigJson(url)) as {
      mcpServers: { omi: Record<string, unknown> };
    };
    expect(parsed.mcpServers.omi).toEqual({
      type: 'http',
      url,
      headers: { Authorization: 'Bearer <key>' },
    });
  });

  it('embeds the given URL and no local transport', () => {
    const json = hostedMcpConfigJson('https://dev.example.com/v1/mcp');
    expect(json).toContain('"url": "https://dev.example.com/v1/mcp"');
    expect(json).not.toContain('docker');
    expect(json).not.toContain('mcp-remote');
    expect(json).not.toContain('command');
  });

  it('stays parseable for a configured base containing quotes or backslashes', () => {
    const mcpUrl = hostedMcpUrl('https://odd"example\\.com/');
    const parsed = JSON.parse(hostedMcpConfigJson(mcpUrl)) as {
      mcpServers: { omi: { url: string } };
    };
    expect(parsed.mcpServers.omi.url).toBe(mcpUrl);
  });
});
