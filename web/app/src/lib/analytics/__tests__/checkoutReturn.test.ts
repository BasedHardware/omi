import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const track = vi.fn();
vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { track: (...args: unknown[]) => track(...args) },
}));
import { openPurchaseCheckout } from '../subscriptionFunnel';

// Execute the real static return scripts, not a parallel fake protocol implementation.
const paymentSource = readFileSync(
  resolve(process.cwd(), '../../backend/routers/payment.py'),
  'utf8',
);
function returnScript(route: 'stripe_success' | 'stripe_cancel') {
  return paymentSource
    .slice(paymentSource.indexOf(`def ${route}(`))
    .match(/<script>([\s\S]*?)<\/script>/)![1];
}
function signal(
  source: Window,
  data: unknown = 'omi:checkout:client_navigation_completed',
  origin = 'https://api.test.invalid',
) {
  window.dispatchEvent(new MessageEvent('message', { source, origin, data }));
}
const completed = () =>
  track.mock.calls.filter(([name]) => name === 'Subscription Checkout Completed');

describe('checkout return navigation observer', () => {
  let checkout: Window;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://api.test.invalid/backend/');
    track.mockReset();
    checkout = { closed: false } as Window;
    vi.spyOn(window, 'open').mockReturnValue(checkout);
  });
  afterEach(() => {
    window.dispatchEvent(new Event('pagehide'));
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('opens first, completes only the exact origin/window static success, once with closed context', () => {
    expect(
      openPurchaseCheckout(
        'https://checkout.test.invalid/private-session',
        'plus',
        'annual',
        'web_plans',
      ),
    ).toBe(checkout);
    expect(track.mock.calls.map(([name]) => name)).toEqual([
      'Subscription Checkout Opened',
    ]);
    signal(checkout, undefined, 'https://api.test.invalid.evil.invalid');
    signal({} as Window);
    signal(checkout, {
      type: 'omi:checkout:client_navigation_completed',
      session_id: 'private',
    });
    window.dispatchEvent(new Event('focus'));
    expect(completed()).toHaveLength(0);
    const opener = {
      postMessage: (data: unknown, target: string) => {
        expect(target).toBe('*');
        signal(checkout, data);
      },
    };
    new Function('window', returnScript('stripe_success'))({ opener });
    signal(checkout);
    expect(completed()).toEqual([
      [
        'Subscription Checkout Completed',
        {
          plan: 'plus',
          billing_interval: 'year',
          source: 'web_plans',
          stage: 'hosted_checkout',
          result: 'client_navigation_completed',
        },
      ],
    ]);
    expect(JSON.stringify(track.mock.calls)).not.toMatch(/private|https:|session_id/);
  });

  it('cancel is terminal; late success and duplicate cancel never complete', () => {
    openPurchaseCheckout('checkout', 'unbounded-plan', 'week', 'unbounded-source');
    new Function('window', returnScript('stripe_cancel'))({
      opener: { postMessage: (data: unknown) => signal(checkout, data) },
    });
    signal(checkout);
    expect(completed()).toHaveLength(0);
    expect(track.mock.calls[0][1]).toMatchObject({
      plan: 'unknown',
      billing_interval: 'unknown',
      source: 'unknown',
    });
  });

  it.each(['closed', 'expired', 'parent-hidden'])(
    'rejects late success after %s',
    (reason) => {
      openPurchaseCheckout('checkout', 'plus', 'month', 'web_plans');
      if (reason === 'closed') Object.assign(checkout, { closed: true });
      if (reason === 'expired') vi.advanceTimersByTime(30 * 60 * 1000);
      if (reason === 'parent-hidden') window.dispatchEvent(new Event('pagehide'));
      signal(checkout);
      expect(completed()).toHaveLength(0);
    },
  );

  it('a blocked or throwing open cannot complete, even with a valid-looking return', () => {
    vi.mocked(window.open)
      .mockReturnValueOnce(null)
      .mockImplementationOnce(() => {
        throw new Error('unavailable');
      });
    expect(openPurchaseCheckout('checkout', 'plus', 'month', 'web_plans')).toBeNull();
    expect(() => openPurchaseCheckout('checkout', 'plus', 'month', 'web_plans')).toThrow(
      'unavailable',
    );
    signal(checkout);
    expect(track).not.toHaveBeenCalled();
  });

  it('observer/analytics faults and absent or isolated openers are fail-open', () => {
    track.mockImplementation(() => {
      throw new Error('sink unavailable');
    });
    vi.spyOn(window, 'addEventListener').mockImplementationOnce(() => {
      throw new Error('observer unavailable');
    });
    expect(openPurchaseCheckout('checkout', 'plus', 'month', 'web_plans')).toBe(checkout);
    expect(() =>
      new Function('window', returnScript('stripe_success'))({ opener: null }),
    ).not.toThrow();
    expect(() =>
      new Function('window', returnScript('stripe_success'))({
        opener: {
          postMessage() {
            throw new Error('isolated');
          },
        },
      }),
    ).not.toThrow();
  });

  it('invalid API configuration disables observation without breaking open', () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'invalid-base');
    expect(openPurchaseCheckout('checkout', 'plus', 'month', 'web_plans')).toBe(checkout);
    signal(checkout);
    expect(completed()).toHaveLength(0);
  });
});
