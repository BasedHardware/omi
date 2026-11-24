import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getCustomerPortal = vi.fn();
const cancelSubscription = vi.fn();

vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    capture: vi.fn(),
    identify: vi.fn(),
    reset: vi.fn(),
    setPersonProperties: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  getAvailablePlans: vi.fn(),
  createCheckoutSession: vi.fn(),
  upgradeSubscription: vi.fn(),
  cancelSubscription: (...args: unknown[]) => cancelSubscription(...args),
  getCustomerPortal: (...args: unknown[]) => getCustomerPortal(...args),
  getUserSubscription: vi.fn(),
}));

import { PlansSheet } from '@/components/settings/PlansSheet';

describe('PlansSheet for a Google Play subscriber', () => {
  it('shows Google Play management instead of Stripe billing, change plan or cancel', () => {
    render(
      <PlansSheet
        open
        onOpenChange={vi.fn()}
        onSubscriptionUpdate={vi.fn()}
        subscription={{
          plan: 'unlimited_v2',
          status: 'active',
          is_unlimited: true,
          current_period_end: Math.floor(Date.UTC(2026, 11, 22) / 1000),
          provider: 'play',
          features: [],
        }}
        cachedPlans={[
          {
            id: 'price_m',
            plan_id: 'unlimited_v2',
            title: 'Monthly',
            price_string: '$29.99/mo',
            interval: 'month',
          },
        ]}
      />,
    );
    expect(screen.getByTestId('plans-play-managed')).toBeTruthy();
    const link = screen.getByRole('link', { name: 'Manage in Google Play' });
    expect(link.getAttribute('href')).toContain(
      'play.google.com/store/account/subscriptions',
    );
    expect(screen.queryByText('Manage Billing & Invoices')).toBeNull();
    expect(screen.queryByText('Cancel Subscription')).toBeNull();
    expect(screen.queryByText('$29.99/mo')).toBeNull();
  });
});
