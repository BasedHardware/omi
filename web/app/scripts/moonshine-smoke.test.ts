import { describe, expect, test } from 'bun:test';
import { GET as searchApps } from '../src/app/api/apps/search/route';
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

  test('serves robots policy through a Moonshine route handler', async () => {
    const response = await robots();
    expect(response.headers.get('content-type')).toContain('text/plain');
    expect(await response.text()).toContain('Sitemap: https://omi.me/sitemap.xml');
  });
});
