import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));
const { getWebDeviceIdHash } = vi.hoisted(() => ({ getWebDeviceIdHash: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));
vi.mock('@/lib/clientDevice', () => ({ getWebDeviceIdHash }));

import { getRecordingPermission } from '@/lib/api';

describe('getRecordingPermission', () => {
  beforeEach(() => {
    getIdToken.mockResolvedValue('test-token');
    getWebDeviceIdHash.mockResolvedValue(null);
    vi.unstubAllGlobals();
  });

  it.each([true, false])(
    'reads store_recording_permission=%s from the backend',
    async (stored) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(JSON.stringify({ store_recording_permission: stored }), {
              headers: { 'content-type': 'application/json' },
            }),
        ),
      );

      expect(await getRecordingPermission()).toEqual({ enabled: stored });
    },
  );
});
