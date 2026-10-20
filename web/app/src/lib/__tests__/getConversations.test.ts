import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { getConversations } from '@/lib/api';

describe('getConversations', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it('asks the server for starred conversations only when starred is set', async () => {
    const fetchMock = vi.fn<
      (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    >(
      async () => new Response('[]', { headers: { 'content-type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getConversations({ starred: true });
    await getConversations();

    const [starredUrl, allUrl] = fetchMock.mock.calls.map(
      ([input]) => new URL(String(input), 'http://localhost'),
    );
    expect(starredUrl.pathname).toBe('/api/proxy/v1/conversations');
    expect(starredUrl.searchParams.get('starred')).toBe('true');
    expect(allUrl.searchParams.has('starred')).toBe(false);
  });
});
