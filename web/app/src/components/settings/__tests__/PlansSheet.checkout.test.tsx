import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const createCheckoutSession = vi.fn(async () => ({
  url: 'https://checkout.stripe.test/pay',
}));

vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    capture: vi.fn(() => {
      throw new Error('localStorage blocked');
    }),
    identify: vi.fn(),
    reset: vi.fn(),
    setPersonProperties: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  getAvailablePlans: vi.fn(),
  createCheckoutSession: (...args: unknown[]) => createCheckoutSession(...args),
  upgradeSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
  getCustomerPortal: vi.fn(),
  getUserSubscription: vi.fn(),
}));

import { PlansSheet } from '@/components/settings/PlansSheet';

describe('PlansSheet checkout', () => {
  beforeEach(() => {
    createCheckoutSession.mockClear();
    vi.stubGlobal('open', vi.fn());
  });

  it('starts checkout when analytics capture throws', async () => {
    render(
      <PlansSheet
        open
        onOpenChange={vi.fn()}
        onSubscriptionUpdate={vi.fn()}
        subscription={{ plan: 'basic', status: 'active', is_unlimited: false }}
        cachedPlans={[
          {
            id: 'price_plus_month',
            plan_id: 'plus',
            title: 'Plus Monthly',
            price_string: '$19',
            interval: 'month',
          },
        ]}
      />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Continue to Payment' }));

    await waitFor(() => {
      expect(createCheckoutSession).toHaveBeenCalledWith('price_plus_month');
    });
    expect(screen.queryByText('An error occurred. Please try again.')).toBeNull();
    expect(window.open).toHaveBeenCalledWith(
      'https://checkout.stripe.test/pay',
      '_blank',
    );
  });
});
