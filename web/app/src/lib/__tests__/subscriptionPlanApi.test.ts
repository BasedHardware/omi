import { afterEach, describe, expect, it, vi } from 'vitest';
import { decodePlan, planGrantsPaidCapability } from '@/types/user';

vi.mock('@/lib/firebase', () => ({
  getIdToken: vi.fn(async () => 'test-token'),
}));

vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn(async () => 'test-device'),
}));

import { getUserSubscription } from '@/lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('getUserSubscription plan decoding', () => {
  it.each([
    ['basic', false],
    ['plus', true],
    ['unlimited', true],
    ['unlimited_v2', true],
    ['operator', true],
    ['architect', true],
    ['pro', true],
    ['future_plan_123', false],
  ])('decodes %s without capability inference', async (raw, expectedPaid) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            subscription: {
              plan: raw,
              status: 'active',
              features: [],
              cancel_at_period_end: false,
            },
          }),
          { headers: { 'content-type': 'application/json' } },
        ),
      ),
    );

    const result = await getUserSubscription();

    expect(result).not.toBeNull();
    expect(result?.plan).toBe(raw);
    expect(result?.plan_identity).toEqual(decodePlan(raw));
    expect(result?.is_unlimited).toBe(expectedPaid);
    expect(result?.is_unlimited).toBe(planGrantsPaidCapability(decodePlan(raw)));
  });
});
