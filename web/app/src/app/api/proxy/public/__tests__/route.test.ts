import { describe, expect, it, vi, afterEach } from 'vitest';
import { GET, isPublicProxyPath } from '@/app/api/proxy/public/[...path]/route';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('public proxy allowlist', () => {
  it('allows the public marketplace and case-status reads', () => {
    expect(isPublicProxyPath('v1/approved-apps')).toBe(true);
    expect(isPublicProxyPath('v2/apps')).toBe(true);
    expect(isPublicProxyPath('v1/fair-use/case/FU-abc123/status')).toBe(true);
  });

  it('refuses anything else, so it is not a credential-free relay', () => {
    expect(isPublicProxyPath('v1/users/me')).toBe(false);
    expect(isPublicProxyPath('v1/memories')).toBe(false);
    expect(isPublicProxyPath('v1/approved-apps/../users')).toBe(false);
  });
});

describe('public proxy handler', () => {
  it('forwards an allowed path to the API without requiring auth', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL) =>
        new Response(JSON.stringify({ groups: [] }), {
          headers: { 'content-type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'https://app.example.com/api/proxy/public/v2/apps?include_reviews=true',
      ),
    );

    expect(response.status).toBe(200);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      'https://api.omi.me/v2/apps?include_reviews=true',
    );
  });

  it('404s a path outside the allowlist', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request('https://app.example.com/api/proxy/public/v1/users/me'),
    );

    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
