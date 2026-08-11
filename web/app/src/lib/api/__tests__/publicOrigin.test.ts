import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { getApprovedApps, getAppsV2, publicApiBaseUrl } from '@/lib/api/public';

/**
 * The backend sets `allow_origins=CORS_ALLOWED_ORIGINS`, which defaults to the
 * empty list (`backend/main.py`), so a browser on the web origin cannot read a
 * direct `https://api.omi.me` response. Every public read made from the client
 * must go to the same-origin passthrough instead.
 */
function stubFetch() {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL) =>
      new Response(JSON.stringify({ plugins: [], stats: [], groups: [] }), {
        headers: { 'content-type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal('window', {});
});

describe('public API origin', () => {
  it('resolves to a same-origin path in the browser', () => {
    expect(publicApiBaseUrl()).toBe('/api/proxy/public');
  });

  it('fetches the marketplace listing same-origin', async () => {
    const fetchMock = stubFetch();
    await getAppsV2(true);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url.startsWith('/api/proxy/public/')).toBe(true);
    expect(url).not.toContain('api.omi.me');
  });

  it('fetches approved apps same-origin', async () => {
    const fetchMock = stubFetch();
    await getApprovedApps();
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url.startsWith('/api/proxy/public/')).toBe(true);
    expect(url).not.toContain('api.omi.me');
  });
});
