import { describe, expect, it, vi } from 'vitest';
import { createFirebaseAuthProxy } from '../../../scripts/firebase-auth-proxy';

describe('same-origin Firebase auth helper proxy', () => {
  it('proxies the iframe without forwarding app credentials or redirecting the browser', async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(
      new Response('helper', {
        headers: {
          'content-type': 'text/html',
          'content-encoding': 'gzip',
          'content-length': '999',
          'content-security-policy': "script-src 'self'; frame-ancestors 'none'",
        },
      }),
    );
    const proxy = createFirebaseAuthProxy('based-hardware', upstream);
    const response = await proxy(
      new Request('https://app.omi.me/__/auth/iframe?apiKey=public&appName=default', {
        headers: { Cookie: 'private=value', Authorization: 'Bearer private' },
      }),
    );
    expect(upstream.mock.calls[0][0]).toBe(
      'https://based-hardware.firebaseapp.com/__/auth/iframe?apiKey=public&appName=default',
    );
    const options = upstream.mock.calls[0][1]!;
    expect(options.redirect).toBe('manual');
    expect(new Headers(options.headers).has('cookie')).toBe(false);
    expect(new Headers(options.headers).has('authorization')).toBe(false);
    expect(await response!.text()).toBe('helper');
    expect(response!.headers.get('x-frame-options')).toBe('SAMEORIGIN');
    expect(response!.headers.get('content-security-policy')).toBe(
      "script-src 'self'; frame-ancestors 'self'",
    );
    expect(response!.headers.get('cache-control')).toBe('no-store');
    expect(response!.headers.has('content-encoding')).toBe(false);
    expect(response!.headers.has('content-length')).toBe(false);
  });

  it('preserves Apple POST callback bytes and Google redirect locations', async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(null, {
        status: 302,
        headers: { Location: 'https://accounts.google.com/example' },
      }),
    );
    const response = await createFirebaseAuthProxy(
      'based-hardware',
      upstream,
    )(
      new Request('https://app.omi.me/__/auth/handler?state=abc', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: 'code=abc&state=xyz',
      }),
    );
    expect(new TextDecoder().decode(upstream.mock.calls[0][1]!.body as ArrayBuffer)).toBe(
      'code=abc&state=xyz',
    );
    expect(response!.status).toBe(302);
    expect(response!.headers.get('location')).toBe('https://accounts.google.com/example');
  });

  it('serves Firebase init configuration and leaves app routes to the normal handler', async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    const proxy = createFirebaseAuthProxy('based-hardware', upstream);
    expect(await proxy(new Request('https://app.omi.me/login?next=%2Fitems'))).toBeNull();
    expect(await proxy(new Request('https://app.omi.me/__/firebase/other'))).toBeNull();
    await proxy(new Request('https://app.omi.me/__/firebase/init.json'));
    expect(upstream).toHaveBeenCalledTimes(1);
    expect(upstream.mock.calls[0][0]).toBe(
      'https://based-hardware.firebaseapp.com/__/firebase/init.json',
    );
  });

  it('fails closed for invalid configuration, unsupported methods and upstream failure', async () => {
    const upstream = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'));
    const request = new Request('https://app.omi.me/__/auth/iframe');
    expect(
      (await createFirebaseAuthProxy('evil.test/path', upstream)(request))!.status,
    ).toBe(503);
    expect(upstream).not.toHaveBeenCalled();
    const proxy = createFirebaseAuthProxy('based-hardware', upstream);
    expect((await proxy(new Request(request, { method: 'DELETE' })))!.status).toBe(405);
    expect(upstream).not.toHaveBeenCalled();
    expect((await proxy(request))!.status).toBe(502);
  });
});
