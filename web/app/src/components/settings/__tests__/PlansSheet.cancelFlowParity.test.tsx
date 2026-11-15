import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const omiFlagEnabled = vi.fn();

vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    capture: vi.fn(),
    identify: vi.fn(),
    reset: vi.fn(),
    setPersonProperties: vi.fn(),
  },
}));

vi.mock('@/lib/omiFlags', () => ({
  omiFlagEnabled: (...args: unknown[]) => omiFlagEnabled(...args),
  resetOmiFlags: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  getAvailablePlans: vi.fn(),
  createCheckoutSession: vi.fn(),
  upgradeSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
  getCustomerPortal: vi.fn(),
  getUserSubscription: vi.fn(),
  getRetentionOffer: vi
    .fn()
    .mockResolvedValue({ eligible: false, percent_off: 50, duration_months: 3 }),
  acceptRetentionOffer: vi.fn(),
}));

import { PlansSheet } from '@/components/settings/PlansSheet';

const plans = [
  {
    id: 'price_plus_month',
    plan_id: 'plus',
    title: 'Plus Monthly',
    price_string: '$19.99/mo',
    interval: 'month',
  },
];

function renderSheet() {
  render(
    <PlansSheet
      open
      onOpenChange={vi.fn()}
      onSubscriptionUpdate={vi.fn()}
      subscription={{
        plan: 'plus',
        status: 'active',
        is_unlimited: true,
        cancel_at_period_end: false,
        current_price_id: 'price_plus_month',
        current_period_end: Math.floor(Date.UTC(2026, 11, 3, 12) / 1000),
        features: [],
      }}
      cachedPlans={plans}
    />,
  );
}

describe('PlansSheet cancel flow kill switch', () => {
  beforeEach(() => {
    omiFlagEnabled.mockReset();
  });

  it('keeps the plain confirm dialog when the flag is unlisted', async () => {
    omiFlagEnabled.mockResolvedValue(undefined);
    renderSheet();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel Subscription' }));
    expect(await screen.findByText('Cancel Subscription?')).toBeTruthy();
    expect(screen.queryByText('Why are you canceling?')).toBeNull();
  });

  it('opens the reason-first flow when the flag is on', async () => {
    omiFlagEnabled.mockResolvedValue(true);
    renderSheet();

    await waitFor(() =>
      expect(omiFlagEnabled).toHaveBeenCalledWith('cancel_flow_parity'),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel Subscription' }));
    expect(await screen.findByText('Why are you canceling?')).toBeTruthy();
    expect(screen.queryByText('Cancel Subscription?')).toBeNull();
  });
});
