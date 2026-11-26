import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { UserSubscription } from '@/types/user';
const state = vi.hoisted(() => ({
  track: vi.fn(),
  checkout: vi.fn(),
  plans: vi.fn(),
  subscription: vi.fn(async (): Promise<UserSubscription | null> => null),
}));
vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track: state.track } }));
vi.mock('@/lib/omiFlags', () => ({ omiFlagEnabled: vi.fn(async () => true) }));
vi.mock('@/lib/api', () => ({
  getAvailablePlans: state.plans,
  createCheckoutSession: state.checkout,
  getUserSubscription: state.subscription,
  upgradeSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
  getCustomerPortal: vi.fn(),
}));
import { PlansSheet } from '../PlansSheet';
const props = {
  onOpenChange: vi.fn(),
  onSubscriptionUpdate: vi.fn(),
  subscription: { plan: 'basic', status: 'active', is_unlimited: false },
  cachedPlans: [
    {
      id: 'price_test',
      plan_id: 'unlimited_v2',
      title: 'Omi Pro Monthly',
      price_string: '$30',
      interval: 'month',
    },
  ],
};
const count = (name: string) =>
  state.track.mock.calls.filter(([event]) => event === `Subscription ${name}`).length;
beforeEach(() => {
  state.track.mockReset();
  state.checkout.mockReset();
  state.plans.mockReset();
  state.subscription.mockReset();
  state.subscription.mockResolvedValue(null);
  window.sessionStorage.clear();
  vi.stubGlobal(
    'open',
    vi.fn(() => ({ closed: true })),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('one view per presentation, none on rerender, new view on reopen', () => {
  const tree = render(<PlansSheet open {...props} />);
  expect(count('Paywall Viewed')).toBe(1);
  tree.rerender(<PlansSheet open {...props} subscription={{ ...props.subscription }} />);
  expect(count('Paywall Viewed')).toBe(1);
  tree.rerender(<PlansSheet open={false} {...props} />);
  tree.rerender(<PlansSheet open {...props} />);
  expect(count('Paywall Viewed')).toBe(2);
});
it('tap precedes URL acquisition; open requires a window; a bare focus is never completion', async () => {
  let release!: (result: { url: string }) => void;
  state.checkout.mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  render(<PlansSheet open {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Continue to Payment' }));
  expect(count('Upgrade Tapped')).toBe(1);
  expect(count('Checkout Opened')).toBe(0);
  expect(count('Checkout Completed')).toBe(0);
  // A focus with no checkout this tab opened is never completion.
  fireEvent.focus(window);
  expect(count('Checkout Completed')).toBe(0);
  release({ url: 'https://checkout.stripe.test/private-session' });
  await waitFor(() => expect(count('Checkout Opened')).toBe(1));
  expect(count('Checkout Completed')).toBe(0);
  const serialized = JSON.stringify(state.track.mock.calls);
  expect(serialized).not.toContain('private-session');
  expect(serialized).not.toContain('price_test');
});
it('one verified paid transition after the checkout tab returns emits one completion', async () => {
  state.checkout.mockResolvedValue({
    url: 'https://checkout.stripe.test/private-session',
  });
  state.subscription.mockResolvedValue({
    plan: 'unlimited_v2',
    status: 'active',
    is_unlimited: true,
  });
  render(<PlansSheet open {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Continue to Payment' }));
  await waitFor(() => expect(count('Checkout Opened')).toBe(1));
  expect(count('Checkout Completed')).toBe(0);

  fireEvent.focus(window);
  await waitFor(() => expect(count('Checkout Completed')).toBe(1));
  const completion = state.track.mock.calls.find(
    ([event]) => event === 'Subscription Checkout Completed',
  );
  expect(completion?.[1]).toMatchObject({
    plan: 'unlimited_v2',
    billing_interval: 'month',
    source: 'web_plans',
    stage: 'hosted_checkout',
  });

  fireEvent.focus(window);
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(count('Checkout Completed')).toBe(1);
  expect(JSON.stringify(state.track.mock.calls)).not.toContain('private-session');
});

it('unmounting removes the checkout return listener and pending record', async () => {
  state.checkout.mockResolvedValue({
    url: 'https://checkout.stripe.test/private-session',
  });
  const tree = render(<PlansSheet open {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Continue to Payment' }));
  await waitFor(() => expect(count('Checkout Opened')).toBe(1));

  tree.unmount();
  fireEvent.focus(window);
  await Promise.resolve();

  expect(state.subscription).not.toHaveBeenCalled();
  expect(count('Checkout Completed')).toBe(0);
  expect(window.sessionStorage.getItem('omi.web.checkout.pending.v1')).toBeNull();
});
it.each(['failed', 'blocked'])(
  'no opened or completion for %s checkout',
  async (result) => {
    if (result === 'failed')
      state.checkout.mockRejectedValue(new Error('private backend error'));
    else {
      state.checkout.mockResolvedValue({ url: 'https://checkout.stripe.test/private' });
      vi.stubGlobal(
        'open',
        vi.fn(() => null),
      );
    }
    render(<PlansSheet open {...props} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to Payment' }));
    await waitFor(() => expect(state.checkout).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Continue to Payment' }),
      ).not.toBeDisabled(),
    );
    expect(count('Upgrade Tapped')).toBe(1);
    expect(count('Checkout Opened')).toBe(0);
    expect(count('Checkout Completed')).toBe(0);
  },
);

it('loading does not consume the view; loaded options count once', async () => {
  let release!: (value: { plans: typeof props.cachedPlans }) => void;
  state.plans.mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const tree = render(<PlansSheet open {...props} cachedPlans={null} />);
  expect(count('Paywall Viewed')).toBe(0);
  release({ plans: props.cachedPlans });
  await waitFor(() => expect(count('Paywall Viewed')).toBe(1));
  tree.rerender(<PlansSheet open {...props} cachedPlans={null} />);
  expect(count('Paywall Viewed')).toBe(1);
});
it.each(['failure', 'empty', 'unknown', 'missing'])(
  'no view for %s plans',
  async (kind) => {
    if (kind === 'failure') state.plans.mockRejectedValue(new Error('private'));
    else
      state.plans.mockResolvedValue({ plans: kind === 'empty' ? [] : props.cachedPlans });
    render(
      <PlansSheet
        open
        {...props}
        cachedPlans={null}
        subscription={
          kind === 'missing'
            ? null
            : kind === 'unknown'
            ? { ...props.subscription, plan: 'future_plan' }
            : props.subscription
        }
      />,
    );
    if (kind !== 'unknown') await waitFor(() => expect(state.plans).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByText('Failed to load plans') !== null).toBe(
        kind === 'failure',
      ),
    );
    expect(count('Paywall Viewed')).toBe(0);
  },
);
