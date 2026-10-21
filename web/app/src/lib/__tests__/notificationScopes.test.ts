import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { getNotificationScopes } from '@/lib/api';

describe('getNotificationScopes', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it('loads the scopes from the route the backend serves', async () => {
    const scopes = [{ id: 'user_name', title: 'User Name' }];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = new URL(String(input), 'https://api.test').pathname;
        if (path.endsWith('/v1/app/proactive-notification-scopes')) {
          return new Response(JSON.stringify(scopes), {
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ detail: 'App not found' }), { status: 404 });
      }),
    );

    expect(await getNotificationScopes()).toEqual(scopes);
  });
});
