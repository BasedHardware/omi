import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn(async () => 'test-token') }));
vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn(async () => 'test-device'),
}));
import { getDeveloperApiKeys, getMcpApiKeys, createDeveloperApiKey } from '@/lib/api';
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
});
