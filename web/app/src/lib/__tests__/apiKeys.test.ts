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
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
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
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[0][0]).toBe('/api/proxy/v1/mcp/keys/scopes');
    const [url, init] = fetch.mock.calls[1];
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
  it('uses the served default scopes instead of the offline literal', async () => {
    const fetch = vi.fn(
      async (url: string, _init?: RequestInit) =>
        new Response(
          JSON.stringify(
            url.endsWith('/scopes')
              ? { client_ids: [], required_scopes: [], default_scopes: ['chat.read'] }
              : { id: 'k1' },
          ),
        ),
    );
    vi.stubGlobal('fetch', fetch);
    await createMcpApiKey('served');
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({
      name: 'served',
      scopes: ['chat.read'],
    });
  });
  it.each([404, 503])(
    'uses offline defaults when the contract returns %s',
    async (status) => {
      const fetch = vi.fn(async (url: string, _init?: RequestInit) =>
        url.endsWith('/scopes')
          ? new Response('{}', { status })
          : new Response('{"id":"k1"}'),
      );
      vi.stubGlobal('fetch', fetch);
      await createMcpApiKey('fallback');
      expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).scopes).toEqual([
        'memories.read',
        'conversations.read',
        'action_items.read',
        'goals.read',
      ]);
    },
  );
  it('preserves explicit scopes without fetching the contract', async () => {
    const fetch = vi.fn(
      async (_url: string, _init?: RequestInit) => new Response('{"id":"k1"}'),
    );
    vi.stubGlobal('fetch', fetch);
    await createMcpApiKey('explicit', ['goals.read']);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      name: 'explicit',
      scopes: ['goals.read'],
    });
  });

  it('aborts a stalled optional contract request and mints with fallback scopes', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn((url: string, init?: RequestInit): Promise<Response> => {
      if (url.endsWith('/scopes')) {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          );
        });
      }
      return Promise.resolve(new Response('{"id":"k1"}'));
    });
    vi.stubGlobal('fetch', fetch);
    const created = createMcpApiKey('bounded');
    await vi.advanceTimersByTimeAsync(5000);
    await expect(created).resolves.toEqual({ id: 'k1' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).scopes).toEqual([
      'memories.read',
      'conversations.read',
      'action_items.read',
      'goals.read',
    ]);
  });
});
