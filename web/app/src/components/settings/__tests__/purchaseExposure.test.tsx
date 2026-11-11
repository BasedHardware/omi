import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({ track: vi.fn(), checkout: vi.fn() }));
vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track: state.track } }));
vi.mock('@/lib/api', () => ({
  getAvailablePlans: vi.fn(),
  createCheckoutSession: state.checkout,
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
  vi.stubGlobal(
    'open',
    vi.fn(() => ({})),
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
it('tap precedes URL acquisition; open requires a window; focus is never completion', async () => {
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
  release({ url: 'https://checkout.stripe.test/private-session' });
  await waitFor(() => expect(count('Checkout Opened')).toBe(1));
  fireEvent.focus(window);
  expect(count('Checkout Completed')).toBe(0);
  const serialized = JSON.stringify(state.track.mock.calls);
  expect(serialized).not.toContain('private-session');
  expect(serialized).not.toContain('price_test');
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
