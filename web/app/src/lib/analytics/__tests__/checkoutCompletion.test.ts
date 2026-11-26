import { beforeEach, describe, expect, it, vi } from 'vitest';

const track = vi.fn();
const flag = vi.fn(async () => true);

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { track: (...args: unknown[]) => track(...args) },
}));

vi.mock('@/lib/omiFlags', () => ({
  omiFlagEnabled: () => flag(),
}));

vi.mock('@/lib/api', () => ({
  getUserSubscription: vi.fn(async () => null),
}));

import {
  completeWebCheckout,
  isVerifiedPaidTransition,
  watchCheckoutReturn,
} from '@/lib/analytics/checkoutCompletion';
import {
  stageWebCheckout,
  takePendingWebCheckout,
} from '@/lib/analytics/checkoutCompletionStore';
import type { UserSubscription } from '@/types/user';

const BEFORE_FREE = {
  plan: 'basic',
  paid: false,
  status: 'active',
  cancelAtPeriodEnd: false,
};

const PAID: UserSubscription = {
  plan: 'unlimited_v2',
  status: 'active',
  is_unlimited: true,
};

const FREE: UserSubscription = {
  plan: 'basic',
  status: 'active',
  is_unlimited: false,
};

const completions = () =>
  track.mock.calls.filter(([event]) => event === 'Subscription Checkout Completed');

function stage({
  before = BEFORE_FREE,
  plan = 'unlimited_v2',
}: {
  before?: typeof BEFORE_FREE;
  plan?: string;
} = {}) {
  return stageWebCheckout({
    plan,
    interval: 'month',
    source: 'web_plans',
    before,
  });
}

describe('web checkout completion', () => {
  beforeEach(() => {
    track.mockClear();
    flag.mockClear();
    flag.mockResolvedValue(true);
    window.sessionStorage.clear();
  });

  it('emits exactly one closed-contract completion for the selected paid transition', async () => {
    const checkoutId = stage();
    const refresh = vi.fn(async () => PAID);

    expect(
      await completeWebCheckout(refresh, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(true);

    expect(completions()).toHaveLength(1);
    expect(completions()[0][1]).toEqual({
      plan: 'unlimited_v2',
      billing_interval: 'month',
      source: 'web_plans',
      stage: 'hosted_checkout',
      result: 'client_navigation_completed',
    });
    // The tab-local checkout id is a dedupe key and never crosses the wire.
    expect(JSON.stringify(track.mock.calls)).not.toContain('checkout_id');
    expect(takePendingWebCheckout()).toBeNull();
  });

  it('a second return inside one checkout window cannot emit again', async () => {
    const checkoutId = stage();

    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(true);
    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(1);
  });

  it('bare focus, reload or a later visit without a staged checkout emits nothing', async () => {
    const refresh = vi.fn(async () => PAID);
    expect(await completeWebCheckout(refresh)).toBe(false);
    expect(refresh).toHaveBeenCalledOnce();
    expect(completions()).toHaveLength(0);
  });

  it('a no-record focus refresh rejection is swallowed', async () => {
    const refresh = vi.fn(async () => {
      throw new Error('refresh failed');
    });
    await expect(completeWebCheckout(refresh)).resolves.toBe(false);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('does not attribute another paid plan to this checkout', async () => {
    const checkoutId = stage();
    const read = vi.fn(async () => ({ ...PAID, plan: 'plus' }));

    expect(
      await completeWebCheckout(async () => undefined, {
        expectedCheckoutId: checkoutId,
        readSubscription: read,
      }),
    ).toBe(false);
    expect(read).toHaveBeenCalledOnce();
    expect(completions()).toHaveLength(0);
  });

  it('requires the selected plan and a change from the saved subscription snapshot', () => {
    const pending = {
      checkoutId: 'x',
      plan: 'unlimited_v2',
      interval: 'month',
      source: 'web_plans',
      before: {
        plan: 'plus',
        paid: true,
        status: 'active',
        cancelAtPeriodEnd: false,
      },
      openedAt: Date.now(),
    };
    expect(isVerifiedPaidTransition(pending, PAID)).toBe(true);
    expect(isVerifiedPaidTransition(pending, { ...PAID, plan: 'architect' })).toBe(false);
    expect(
      isVerifiedPaidTransition(
        { ...pending, before: { ...pending.before, plan: 'unlimited_v2' } },
        PAID,
      ),
    ).toBe(false);
    expect(isVerifiedPaidTransition(pending, { ...PAID, plan: 'unknown' })).toBe(false);
  });

  it('does not emit for a null refresh result, a rejected refresh or an unpaid state', async () => {
    const read = vi.fn(async () => PAID);

    const nullId = stage();
    expect(
      await completeWebCheckout(async () => null, {
        expectedCheckoutId: nullId,
        readSubscription: read,
      }),
    ).toBe(false);

    const rejectedId = stage();
    expect(
      await completeWebCheckout(
        async () => {
          throw new Error('refresh failed');
        },
        { expectedCheckoutId: rejectedId, readSubscription: read },
      ),
    ).toBe(false);

    const unpaidId = stage();
    expect(
      await completeWebCheckout(async () => FREE, {
        expectedCheckoutId: unpaidId,
        readSubscription: read,
      }),
    ).toBe(false);

    expect(read).not.toHaveBeenCalled();
    expect(completions()).toHaveLength(0);
  });

  it('an inactive paid snapshot is not a verified transition', () => {
    const checkoutId = stage();
    expect(checkoutId).toBeTruthy();
    const pending = takePendingWebCheckout();
    expect(isVerifiedPaidTransition(pending!, { ...PAID, status: 'inactive' })).toBe(
      false,
    );
  });

  it('the kill switch being explicitly off suppresses emission', async () => {
    flag.mockResolvedValue(false);
    const checkoutId = stage();
    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
    expect(takePendingWebCheckout()).toBeNull();
  });

  it('a default-on flag read still emits when the flag store cannot answer', async () => {
    flag.mockRejectedValue(new Error('flag store down'));
    const checkoutId = stage();
    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(true);
  });

  it('unavailable storage means no verified completion path', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    expect(stage()).toBeNull();
    setItem.mockRestore();

    expect(await completeWebCheckout(async () => PAID)).toBe(false);
    expect(completions()).toHaveLength(0);
  });

  it('a stale record is discarded', () => {
    window.sessionStorage.setItem(
      'omi.web.checkout.pending.v1',
      JSON.stringify({
        checkoutId: 'old',
        plan: 'unlimited_v2',
        interval: 'month',
        source: 'web_plans',
        before: BEFORE_FREE,
        openedAt: Date.now() - 61 * 60 * 1000,
      }),
    );
    expect(takePendingWebCheckout()).toBeNull();
    expect(window.sessionStorage.getItem('omi.web.checkout.pending.v1')).toBeNull();
  });

  it('the refresh result is used without a second subscription read', async () => {
    const checkoutId = stage();
    const read = vi.fn(async () => null);
    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
        readSubscription: read,
      }),
    ).toBe(true);
    expect(read).not.toHaveBeenCalled();
    expect(completions()).toHaveLength(1);
  });

  it('a void refresh uses at most one authoritative read', async () => {
    const checkoutId = stage();
    let reads = 0;
    expect(
      await completeWebCheckout(async () => undefined, {
        expectedCheckoutId: checkoutId,
        readSubscription: async () => {
          reads += 1;
          return PAID;
        },
      }),
    ).toBe(true);
    expect(reads).toBe(1);
    expect(completions()).toHaveLength(1);
  });

  it('a failed storage removal fails closed', async () => {
    const checkoutId = stage();
    const removeItem = vi
      .spyOn(Storage.prototype, 'removeItem')
      .mockImplementation(() => {
        throw new Error('storage denied');
      });

    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: checkoutId,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
    removeItem.mockRestore();
  });

  it('overlapping checkouts invalidate both completion signals', async () => {
    const firstCheckoutId = stage();
    const secondCheckoutId = stage();
    expect(firstCheckoutId).toBeTruthy();
    expect(secondCheckoutId).toBeNull();
    expect(
      await completeWebCheckout(async () => PAID, {
        expectedCheckoutId: firstCheckoutId,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
  });

  it('refreshes on early focus without consuming completion until checkout closes', async () => {
    const checkoutId = stage();
    const checkoutState = { closed: false };
    const checkoutWindow = checkoutState as Window;
    const refresh = vi.fn(async () => PAID);
    const cleanup = watchCheckoutReturn(refresh, { checkoutWindow, checkoutId });

    window.dispatchEvent(new Event('focus'));
    expect(refresh).toHaveBeenCalledOnce();
    expect(completions()).toHaveLength(0);
    expect(window.sessionStorage.getItem('omi.web.checkout.pending.v1')).not.toBeNull();

    checkoutState.closed = true;
    window.dispatchEvent(new Event('focus'));
    await vi.waitFor(() => expect(completions()).toHaveLength(1));
    window.dispatchEvent(new Event('focus'));
    expect(refresh).toHaveBeenCalledTimes(2);
    expect(completions()).toHaveLength(1);
    cleanup();
  });

  it('component cleanup removes its listener and pending record', async () => {
    const checkoutId = stage();
    const checkoutWindow = { closed: true } as Window;
    const refresh = vi.fn(async () => PAID);
    const cleanup = watchCheckoutReturn(refresh, { checkoutWindow, checkoutId });

    cleanup();
    window.dispatchEvent(new Event('focus'));
    await Promise.resolve();
    expect(refresh).not.toHaveBeenCalled();
    expect(completions()).toHaveLength(0);
    expect(window.sessionStorage.getItem('omi.web.checkout.pending.v1')).toBeNull();
  });
});
