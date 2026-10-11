import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { updatePersonName } from '@/lib/api';

describe('updatePersonName', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it('sends the new name as the value query param the backend reads', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ status: 'ok' }), {
          headers: { 'content-type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await updatePersonName('person-1', 'Ann & Bo #2');

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(String(input), 'https://api.test');
    expect(url.pathname).toMatch(/\/v1\/users\/people\/person-1\/name$/);
    expect(url.searchParams.get('value')).toBe('Ann & Bo #2');
    expect(init?.method).toBe('PATCH');
    expect(init?.body).toBeUndefined();
  });
});
