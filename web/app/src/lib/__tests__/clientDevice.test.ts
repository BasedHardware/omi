import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getWebDeviceIdHash } from '@/lib/clientDevice';

const WEB_DEVICE_ID_KEY = 'omi-web-device-id';

describe('web client device identity', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('persists a cryptographically random device id for a stable provenance hash', async () => {
    const randomValues = vi.spyOn(globalThis.crypto, 'getRandomValues');

    const firstHash = await getWebDeviceIdHash();
    const savedDeviceId = localStorage.getItem(WEB_DEVICE_ID_KEY);
    const secondHash = await getWebDeviceIdHash();

    expect(savedDeviceId).toMatch(/^web_\d+_[0-9a-f]{32}$/);
    expect(firstHash).toMatch(/^[0-9a-f]{8}$/);
    expect(secondHash).toBe(firstHash);
    expect(randomValues).toHaveBeenCalledTimes(1);
  });
});
