import { describe, expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { GET as searchApps } from '../src/app/api/apps/search/route';
import { POST as exchangeWebAuthToken } from '../src/app/api/auth/token/route';
import { GET as proxy } from '../src/app/api/proxy/[...path]/route';
import { GET as robots } from '../src/app/robots.txt/route';

describe('Moonshine web routes', () => {
  test('returns an empty result for a blank app search', async () => {
    const response = await searchApps(new Request('http://localhost/api/apps/search?q='));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ results: [], count: 0, query: '' });
  });

  test('fails closed when the API proxy has no auth header', async () => {
    const response = await proxy(new Request('http://localhost/api/proxy/v1/health'));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: 'Authorization header required' });
  });

  test('forwards only the web auth token exchange fields', async () => {
    const previousFetch = globalThis.fetch;
    let receivedBody = '';
    const mockFetch = async (
      _input: Parameters<typeof fetch>[0],
      init?: Parameters<typeof fetch>[1],
    ) => {
      receivedBody = String(init?.body || '');
      return new Response(JSON.stringify({ custom_token: 'test-token' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    };
    globalThis.fetch = Object.assign(mockFetch, { preconnect: previousFetch.preconnect });

    try {
      const response = await exchangeWebAuthToken(
        new Request('http://localhost/api/auth/token', {
          method: 'POST',
          body: new URLSearchParams({
            grant_type: 'authorization_code',
            code: 'test-code',
            redirect_uri: 'https://web.example/login',
            use_custom_token: 'true',
            code_verifier: 'test-verifier',
            ignored: 'not-forwarded',
          }),
        }),
      );
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ custom_token: 'test-token' });
      expect(receivedBody).toBe(
        'grant_type=authorization_code&code=test-code&redirect_uri=https%3A%2F%2Fweb.example%2Flogin&use_custom_token=true&code_verifier=test-verifier',
      );
    } finally {
      globalThis.fetch = previousFetch;
    }
  });

  test('serves robots policy through a Moonshine route handler', async () => {
    const response = await robots();
    expect(response.headers.get('content-type')).toContain('text/plain');
    expect(await response.text()).toContain('Sitemap: https://omi.me/sitemap.xml');
  });

  test('renders a ready public-build canary without waiting for hydration', async () => {
    const names = [
      'NEXT_PUBLIC_API_BASE_URL',
      'NEXT_PUBLIC_FIREBASE_API_KEY',
      'NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN',
      'NEXT_PUBLIC_FIREBASE_PROJECT_ID',
      'NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET',
      'NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID',
      'NEXT_PUBLIC_FIREBASE_APP_ID',
      'NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID',
      'NEXT_PUBLIC_FIREBASE_VAPID_KEY',
    ];
    const previous = new Map(names.map((name) => [name, process.env[name]]));
    try {
      for (const name of names) process.env[name] = 'test-value';
      const { PublicBuildCanary } = await import('../src/components/public-build-canary');
      expect(renderToStaticMarkup(PublicBuildCanary())).toContain(
        'data-omi-public-build-canary="app:ready"',
      );
    } finally {
      for (const [name, value] of previous) {
        if (value === undefined) delete process.env[name];
        else process.env[name] = value;
      }
    }
  });
});
