import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ getClientFlags: vi.fn() }));

import { loadOmiFlags, omiFlagEnabled, resetOmiFlags } from '@/lib/omiFlags';

const response = {
  version: 3,
  flags: [
    { key: 'web-plan-storefront', enabled: false },
    { key: 'web-contextual-upsells', enabled: true },
  ],
};

describe('omiFlags', () => {
  beforeEach(() => resetOmiFlags());

  it('answers owned keys and leaves unowned keys to PostHog', async () => {
    const load = vi.fn().mockResolvedValue(response);
    expect(await omiFlagEnabled('web-plan-storefront', { load })).toBe(false);
    expect(await omiFlagEnabled('web-contextual-upsells', { load })).toBe(true);
    expect(await omiFlagEnabled('not-migrated', { load })).toBeUndefined();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('a failed fetch reads as unknown and the next read retries', async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error('Not authenticated'))
      .mockResolvedValue(response);
    expect(await omiFlagEnabled('web-plan-storefront', { load })).toBeUndefined();
    expect(await omiFlagEnabled('web-plan-storefront', { load })).toBe(false);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('a slow store times out to unknown', async () => {
    const load = () => new Promise<typeof response>(() => {});
    expect(
      await omiFlagEnabled('web-plan-storefront', { load, timeoutMs: 5 }),
    ).toBeUndefined();
  });

  it('reset fetches the next account', async () => {
    const load = vi.fn().mockResolvedValue(response);
    await loadOmiFlags(load);
    resetOmiFlags();
    await loadOmiFlags(load);
    expect(load).toHaveBeenCalledTimes(2);
  });
});
