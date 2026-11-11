import { afterEach, describe, expect, it, vi } from 'vitest';
import { GET, POST } from '@/app/api/proxy/[...path]/route';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('authenticated proxy handler', () => {
  it('passes binary image bodies through byte-for-byte', async () => {
    // PNG signature followed by bytes that are invalid UTF-8; a text round-trip
    // replaces them with U+FFFD and the browser can no longer decode the image.
    const png = new Uint8Array([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0xfe, 0x00, 0x80,
    ]);
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(png, {
          headers: {
            'content-type': 'image/png',
            'cache-control': 'private, max-age=86400',
          },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'https://app.example.com/api/proxy/v1/static-map?pins=37.7749%2C-122.4194&width=320&height=200',
        { headers: { Authorization: 'Bearer test-token' } },
      ),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('image/png');
    expect(response.headers.get('cache-control')).toBe('private, max-age=86400');
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(png);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      'https://api.omi.me/v1/static-map?pins=37.7749%2C-122.4194&width=320&height=200',
    );
  });

  it('streams event-stream replies while the upstream is still sending', async () => {
    let upstream!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        upstream = controller;
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (_input: RequestInfo | URL, _init?: RequestInit) =>
          new Response(body, { headers: { 'content-type': 'text/event-stream' } }),
      ),
    );
    upstream.enqueue(new TextEncoder().encode('data: first\n\n'));

    const response = await POST(
      new Request('https://app.example.com/api/proxy/v2/messages', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer test-token',
          'content-type': 'application/json',
        },
        body: JSON.stringify({ text: 'hi' }),
      }),
    );
    const reader = response.body!.getReader();
    const first = await reader.read();

    expect(response.headers.get('content-type')).toBe('text/event-stream');
    expect(new TextDecoder().decode(first.value)).toBe('data: first\n\n');
    upstream.close();
    expect((await reader.read()).done).toBe(true);
  }, 2000);

  it('refuses to forward a request without an Authorization header', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await GET(
      new Request(
        'https://app.example.com/api/proxy/v1/static-map?pins=1%2C1&width=64&height=64',
      ),
    );

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
