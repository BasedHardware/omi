import { describe, expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { GET as searchApps } from '../src/app/api/apps/search/route';
import { GET as proxy } from '../src/app/api/proxy/[...path]/route';
import { GET as robots } from '../src/app/robots.txt/route';
import { buildPublicEnvironment, deriveWebSocketBaseUrl } from './copy-moonshine-assets';

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

  test('derives recording WebSockets from the selected API environment', () => {
    expect(deriveWebSocketBaseUrl('https://api.omiapi.com')).toBe('wss://api.omiapi.com');
    expect(deriveWebSocketBaseUrl('http://localhost:8000')).toBe('ws://localhost:8000');
    expect(
      buildPublicEnvironment({
        NEXT_PUBLIC_API_BASE_URL: 'https://api.omiapi.com',
      }).NEXT_PUBLIC_WS_BASE_URL,
    ).toBe('wss://api.omiapi.com');
    expect(
      buildPublicEnvironment({
        NEXT_PUBLIC_API_BASE_URL: 'https://api.omiapi.com',
        NEXT_PUBLIC_WS_BASE_URL: 'wss://recording.example.com',
      }).NEXT_PUBLIC_WS_BASE_URL,
    ).toBe('wss://recording.example.com');
  });
});
