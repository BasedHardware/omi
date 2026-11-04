import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const createCheckoutSession = vi.fn(async (_priceId: string) => ({
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
  createCheckoutSession: (priceId: string) => createCheckoutSession(priceId),
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

  it('renders a single-plan Omi Pro catalog as two intervals and checks out the selected one', async () => {
    // 2026-10-24 ruling: a new buyer's web catalog is unlimited_v2 only.
    // The sheet renders both billing intervals of the single tier, preselects
    // the first, checks out the selected price, and shows no other tier.
    render(
      <PlansSheet
        open
        onOpenChange={vi.fn()}
        onSubscriptionUpdate={vi.fn()}
        subscription={{ plan: 'basic', status: 'active', is_unlimited: false }}
        cachedPlans={[
          {
            id: 'price_omi_pro_month',
            plan_id: 'unlimited_v2',
            title: 'Unlimited Monthly',
            price_string: '$29.99/mo',
            interval: 'month',
          },
          {
            id: 'price_omi_pro_year',
            plan_id: 'unlimited_v2',
            title: 'Unlimited Annual',
            price_string: '$22.49/mo',
            interval: 'year',
          },
        ]}
      />,
    );

    expect(await screen.findByText('Unlimited Monthly')).toBeTruthy();
    expect(screen.getByText('Unlimited Annual')).toBeTruthy();
    expect(screen.queryByText('Plus Monthly')).toBeNull();

    // Annual is selectable and becomes the checkout target.
    fireEvent.click(screen.getByRole('button', { name: /Unlimited Annual/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    await waitFor(() => {
      expect(createCheckoutSession).toHaveBeenCalledWith('price_omi_pro_year');
    });
    expect(window.open).toHaveBeenCalledWith(
      'https://checkout.stripe.test/pay',
      '_blank',
    );
  });
});
