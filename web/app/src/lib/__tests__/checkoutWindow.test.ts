import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const track = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track } }));
import { openCheckoutWindow } from '../checkoutWindow';

const url = 'https://checkout.stripe.test/pay';
const selection = { plan: 'unlimited_v2', billingInterval: 'year', source: 'web_plans' };
beforeEach(() => track.mockClear());
afterEach(() => vi.unstubAllGlobals());

describe('checkout browser launch', () => {
  it.each(['null', 'exception'])(
    'reports a blocked %s launch with one event after the attempt',
    (failure) => {
      vi.stubGlobal(
        'open',
        vi.fn(() => {
          expect(track).not.toHaveBeenCalled();
          if (failure === 'exception') throw new Error('browser denied');
          return null;
        }),
      );
      expect(openCheckoutWindow(url, selection)).toBe(false);
      expect(track).toHaveBeenCalledExactlyOnceWith('Upgrade Plan Selected', {
        plan: 'unlimited_v2',
        billing_interval: 'year',
        source: 'web_plans',
        launch_result: 'blocked',
      });
    },
  );

  it('nulls the opener and keeps the URL/target without the noopener feature', () => {
    const checkout = { opener: window };
    const open = vi.fn(() => {
      expect(track).not.toHaveBeenCalled();
      return checkout;
    });
    vi.stubGlobal('open', open);
    expect(openCheckoutWindow(url, selection)).toBe(true);
    expect(open).toHaveBeenCalledExactlyOnceWith(url, '_blank');
    expect(checkout.opener).toBeNull();
    expect(track).toHaveBeenCalledExactlyOnceWith('Upgrade Plan Selected', {
      plan: 'unlimited_v2',
      billing_interval: 'year',
      source: 'web_plans',
      launch_result: 'opened',
    });
  });

  it('still reports opened when browser policy rejects changing the opener', () => {
    const checkout = Object.defineProperty({}, 'opener', {
      set() {
        throw new Error('denied');
      },
    });
    vi.stubGlobal(
      'open',
      vi.fn(() => checkout),
    );
    expect(openCheckoutWindow(url, selection)).toBe(true);
    expect(track).toHaveBeenCalledExactlyOnceWith(
      'Upgrade Plan Selected',
      expect.objectContaining({ launch_result: 'opened' }),
    );
  });
});
