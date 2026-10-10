import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/firebase', () => ({ getIdToken: vi.fn(async () => 'test-token') }));
vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn(async () => 'test-device'),
}));

import {
  deleteAppWebhookSigningSecret,
  deleteDeveloperWebhookSigningSecret,
  getAppWebhookSigningSecretStatus,
  getDeveloperWebhookSigningSecretStatus,
  issueAppWebhookSigningSecret,
  issueDeveloperWebhookSigningSecret,
} from '@/lib/api';

afterEach(() => vi.unstubAllGlobals());

function stubJson(body: unknown, status = 200) {
  const fetch = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function requestOf(fetch: ReturnType<typeof vi.fn>) {
  const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
  return { url, method: init.method ?? 'GET', headers: new Headers(init.headers) };
}

describe('developer webhook signing secret API', () => {
  it('reads status, issues through POST and deletes through DELETE on one path', async () => {
    let fetch = stubJson({ configured: false });
    await expect(getDeveloperWebhookSigningSecretStatus()).resolves.toEqual({
      configured: false,
    });
    expect(requestOf(fetch)).toMatchObject({
      url: '/api/proxy/v1/users/developer/webhook-signing-secret',
      method: 'GET',
    });

    fetch = stubJson({
      secret: 'whsec_x',
      created_at: '2026-10-08T12:00:00+00:00',
      previous_valid_until: null,
    });
    const issued = await issueDeveloperWebhookSigningSecret();
    expect(issued.secret).toBe('whsec_x');
    expect(requestOf(fetch)).toMatchObject({
      url: '/api/proxy/v1/users/developer/webhook-signing-secret',
      method: 'POST',
    });
    expect(requestOf(fetch).headers.get('authorization')).toBe('Bearer test-token');

    fetch = stubJson({ status: 'ok' });
    await expect(deleteDeveloperWebhookSigningSecret()).resolves.toBeUndefined();
    expect(requestOf(fetch).method).toBe('DELETE');
  });

  it('surfaces a failed issue as a rejection instead of a fake secret', async () => {
    stubJson({ detail: 'nope' }, 500);
    await expect(issueDeveloperWebhookSigningSecret()).rejects.toThrow('API error: 500');
  });
});

describe('integration-app webhook signing secret API', () => {
  it('addresses the app by id on every verb', async () => {
    let fetch = stubJson({ configured: true, created_at: '2026-10-08T12:00:00+00:00' });
    await expect(getAppWebhookSigningSecretStatus('app 1')).resolves.toMatchObject({
      configured: true,
    });
    expect(requestOf(fetch)).toMatchObject({
      url: '/api/proxy/v1/apps/app%201/webhook-signing-secret',
      method: 'GET',
    });

    fetch = stubJson({ secret: 'whsec_app', created_at: '2026-10-08T12:00:00+00:00' });
    await expect(issueAppWebhookSigningSecret('app-1')).resolves.toMatchObject({
      secret: 'whsec_app',
    });
    expect(requestOf(fetch)).toMatchObject({
      url: '/api/proxy/v1/apps/app-1/webhook-signing-secret',
      method: 'POST',
    });

    fetch = stubJson({ status: 'ok' });
    await deleteAppWebhookSigningSecret('app-1');
    expect(requestOf(fetch)).toMatchObject({
      url: '/api/proxy/v1/apps/app-1/webhook-signing-secret',
      method: 'DELETE',
    });
  });

  it('propagates the owner check as an error', async () => {
    stubJson({ detail: 'You are not authorized' }, 403);
    await expect(getAppWebhookSigningSecretStatus('app-1')).rejects.toThrow(
      'API error: 403',
    );
  });
});
