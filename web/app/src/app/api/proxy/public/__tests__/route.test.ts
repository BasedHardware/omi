import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  GET,
  isPublicProxyPath,
  publicProxyCacheControl,
} from '@/app/api/proxy/public/[...path]/route';

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

describe('public proxy upstream handling', () => {
  it('caches a success but never an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('{}', { headers: { 'content-type': 'application/json' } }),
      ),
    );
    const good = await GET(new Request('https://app.omi.me/api/proxy/public/v2/apps'));
    expect(good.headers.get('Cache-Control')).toContain('max-age');

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('nope', { status: 503 })),
    );
    const bad = await GET(new Request('https://app.omi.me/api/proxy/public/v2/apps'));
    // A cached 503 would outlive the outage that produced it.
    expect(bad.headers.get('Cache-Control')).toBeNull();
  });

  it('never caches changing fair-use case status', async () => {
    expect(publicProxyCacheControl('v1/fair-use/case/FU-abc123/status', true)).toBe(
      'no-store',
    );
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('{"stage":"warning"}', {
            headers: { 'content-type': 'application/json' },
          }),
      ),
    );

    const response = await GET(
      new Request(
        'https://app.omi.me/api/proxy/public/v1/fair-use/case/FU-abc123/status',
      ),
    );

    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });

  it('bounds the wait on the backend rather than holding the connection open', async () => {
    let sawSignal = false;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        sawSignal = Boolean(init?.signal);
        return new Response('{}', { headers: { 'content-type': 'application/json' } });
      }),
    );
    await GET(new Request('https://app.omi.me/api/proxy/public/v2/apps'));
    expect(sawSignal).toBe(true);
  });

  it('answers 502 when the backend times out instead of hanging', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new DOMException('The operation was aborted.', 'TimeoutError');
      }),
    );
    const response = await GET(
      new Request('https://app.omi.me/api/proxy/public/v2/apps'),
    );
    expect(response.status).toBe(502);
  });
});
