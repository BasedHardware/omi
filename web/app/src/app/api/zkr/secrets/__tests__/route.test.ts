import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../route';
import { prepareZkrShare } from '@/lib/zkr';

function post(body: unknown, headers: Record<string, string> = {}) {
  return POST(
    new Request('https://app.omi.me/api/zkr/secrets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: typeof body === 'string' ? body : JSON.stringify(body),
    }),
  );
}

describe('zkr relay route', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('forwards a valid ciphertext-only request to zkr unchanged', async () => {
    const upstream = vi.fn(async (_url: string, _init?: RequestInit) =>
      Response.json(
        { v: 1, id: 'AbCdEfGhIjKlMnOpQrStUv', expiresAt: 'soon' },
        { status: 201 },
      ),
    );
    vi.stubGlobal('fetch', upstream);
    const { request } = await prepareZkrShare('omi_mcp_secret');

    const response = await post(request, { 'Sec-Fetch-Site': 'same-origin' });

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({
      id: 'AbCdEfGhIjKlMnOpQrStUv',
      expiresAt: 'soon',
    });
    expect(upstream).toHaveBeenCalledTimes(1);
    const [url, init] = upstream.mock.calls[0];
    expect(url).toBe('https://zkr.scalingforever.com/api/v1/secrets');
    expect(JSON.parse(String(init?.body))).toEqual(request);
  });

  it('refuses cross-site callers and anything but a key-sized one-time share', async () => {
    const upstream = vi.fn();
    vi.stubGlobal('fetch', upstream);
    const { request } = await prepareZkrShare('omi_mcp_secret');

    expect((await post(request, { 'Sec-Fetch-Site': 'cross-site' })).status).toBe(403);
    expect((await post({ ...request, expiresInSeconds: 604800 })).status).toBe(400);
    expect((await post({ ...request, secret: 'omi_mcp_secret' })).status).toBe(400);
    expect((await post('not json')).status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });

  it('reports an upstream failure without echoing its body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: 'x' }, { status: 429 })),
    );
    const { request } = await prepareZkrShare('omi_mcp_secret');
    const response = await post(request);
    expect(response.status).toBe(429);
    expect(await response.json()).toEqual({
      error: 'Secure link service rejected the request',
    });
  });
});
