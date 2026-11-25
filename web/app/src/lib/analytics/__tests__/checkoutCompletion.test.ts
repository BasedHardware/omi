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

function stage(paidBefore = false) {
  stageWebCheckout({
    plan: 'unlimited_v2',
    interval: 'month',
    source: 'web_plans',
    paidBefore,
  });
}

describe('web checkout completion', () => {
  beforeEach(() => {
    track.mockClear();
    flag.mockClear();
    flag.mockResolvedValue(true);
    window.sessionStorage.clear();
  });

  it('emits exactly one closed-contract completion for a verified paid transition', async () => {
    stage();
    const refresh = vi.fn(async () => null);

    expect(
      await completeWebCheckout(refresh, {
        attempts: 1,
        readSubscription: async () => PAID,
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
    stage();
    const read = async () => PAID;

    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: read,
      }),
    ).toBe(true);
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: read,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(1);
  });

  it('bare focus, reload or a later visit without a staged checkout emits nothing', async () => {
    const refresh = vi.fn(async () => null);
    expect(
      await completeWebCheckout(refresh, {
        attempts: 1,
        readSubscription: async () => PAID,
      }),
    ).toBe(false);
    expect(refresh).toHaveBeenCalledOnce();
    expect(completions()).toHaveLength(0);
  });

  it('fails closed when the subscription read is null, throws or is not paid', async () => {
    stage();
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => null,
      }),
    ).toBe(false);

    stage();
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => {
          throw new Error('network');
        },
      }),
    ).toBe(false);

    stage();
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => FREE,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
  });

  it('an inactive paid snapshot is not a verified transition', async () => {
    stage();
    await completeWebCheckout(async () => null, {
      attempts: 1,
      readSubscription: async () => ({ ...PAID, status: 'inactive' }),
    });
    expect(completions()).toHaveLength(0);
  });

  it('a paid snapshot that did not move is not a new checkout completion', () => {
    const pending = {
      checkoutId: 'x',
      plan: 'unlimited_v2',
      interval: 'month',
      source: 'web_plans',
      paidBefore: true,
      openedAt: Date.now(),
    };
    expect(isVerifiedPaidTransition(pending, PAID)).toBe(false);
    expect(isVerifiedPaidTransition({ ...pending, plan: 'plus' }, PAID)).toBe(true);
  });

  it('the kill switch being explicitly off suppresses the event without touching exposure events', async () => {
    flag.mockResolvedValue(false);
    stage();
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => PAID,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
    // The record is consumed so a later focus cannot resurrect it.
    expect(takePendingWebCheckout()).toBeNull();
  });

  it('a default-on flag read still emits when the flag store cannot answer', async () => {
    flag.mockRejectedValue(new Error('flag store down'));
    stage();
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => PAID,
      }),
    ).toBe(true);
  });

  it('unavailable storage means no verified completion path', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    stage();
    setItem.mockRestore();

    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => PAID,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
  });

  it('a stale record is discarded', async () => {
    window.sessionStorage.setItem(
      'omi.web.checkout.pending.v1',
      JSON.stringify({
        checkoutId: 'old',
        plan: 'unlimited_v2',
        interval: 'month',
        source: 'web_plans',
        paidBefore: false,
        openedAt: Date.now() - 61 * 60 * 1000,
      }),
    );
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 1,
        readSubscription: async () => PAID,
      }),
    ).toBe(false);
    expect(completions()).toHaveLength(0);
  });

  it('the refresh result is used as the verified read when it is a subscription', async () => {
    stage();
    const read = vi.fn(async () => null);
    expect(
      await completeWebCheckout(async () => PAID, {
        attempts: 1,
        readSubscription: read,
      }),
    ).toBe(true);
    expect(read).not.toHaveBeenCalled();
    expect(completions()).toHaveLength(1);
  });

  it('watchCheckoutReturn is single-shot', async () => {
    stage();
    const refresh = vi.fn(async () => PAID);
    watchCheckoutReturn(refresh);
    window.dispatchEvent(new Event('focus'));
    window.dispatchEvent(new Event('focus'));
    await vi.waitFor(() => expect(completions()).toHaveLength(1));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it('retries absorb webhook lag without emitting twice', async () => {
    stage();
    let reads = 0;
    const read = async () => {
      reads += 1;
      return reads >= 2 ? PAID : FREE;
    };
    expect(
      await completeWebCheckout(async () => null, {
        attempts: 3,
        retryDelayMs: 1,
        readSubscription: read,
      }),
    ).toBe(true);
    expect(completions()).toHaveLength(1);
  });
});
