import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn(async () => 'test-token') }));
vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn(async () => 'test-device'),
}));
import {
  getDeveloperApiKeys,
  getMcpApiKeys,
  createDeveloperApiKey,
  createMcpApiKey,
} from '@/lib/api';
afterEach(() => vi.unstubAllGlobals());
describe('key API error handling', () => {
  it.each([getDeveloperApiKeys, getMcpApiKeys])(
    'preserves soft failures and allows strict lists',
    async (getKeys) => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
      await expect(getKeys()).resolves.toEqual([]);
      await expect(getKeys({ throwOnError: true })).rejects.toThrow('offline');
    },
  );
  it.each([getDeveloperApiKeys, getMcpApiKeys])(
    'returns a genuine empty strict list',
    async (getKeys) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response('[]')),
      );
      await expect(getKeys({ throwOnError: true })).resolves.toEqual([]);
    },
  );
  it('rejects explicitly empty scopes before fetching', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(createDeveloperApiKey('name', [])).rejects.toThrow(
      'Select at least one permission',
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it('sends explicit read-only scopes when creating an MCP API key', async () => {
    const fetch = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            id: 'k1',
            name: 'Claude Code',
            key_prefix: 'omi_mcp_1234',
            key: 'omi_mcp_0123456789abcdef0123456789abcdef',
            created_at: '2026-10-18T00:00:00Z',
          }),
        ),
    );
    vi.stubGlobal('fetch', fetch);
    await createMcpApiKey('Claude Code');
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('/api/proxy/v1/mcp/keys');
    expect(init?.method).toBe('POST');
    const body = JSON.parse(String(init?.body));
    expect(body).toEqual({
      name: 'Claude Code',
      scopes: ['memories.read', 'conversations.read', 'action_items.read', 'goals.read'],
    });
    expect(body.scopes).not.toContain('memories.write');
    expect(body.scopes).not.toContain('action_items.write');
    expect(body.scopes).not.toContain('screen_activity.read');
    expect(body.scopes).not.toContain('people.read');
    expect(body.scopes).not.toContain('people.rename');
  });
});
