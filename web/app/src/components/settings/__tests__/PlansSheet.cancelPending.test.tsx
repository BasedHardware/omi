import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const createCheckoutSession = vi.fn();
const upgradeSubscription = vi.fn();

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
  createCheckoutSession: (...args: unknown[]) => createCheckoutSession(...args),
  upgradeSubscription: (...args: unknown[]) => upgradeSubscription(...args),
  cancelSubscription: vi.fn(),
  getCustomerPortal: vi.fn(),
  getUserSubscription: vi.fn(),
}));

import { PlansSheet } from '@/components/settings/PlansSheet';

const periodEnd = Math.floor(Date.UTC(2026, 10, 3, 12) / 1000);
const dateLabel = new Date(periodEnd * 1000).toLocaleDateString('en-US', {
  month: 'long',
  day: 'numeric',
  year: 'numeric',
});

const plans = [
  {
    id: 'price_plus_month',
    plan_id: 'plus',
    title: 'Plus Monthly',
    price_string: '$19.99/mo',
    interval: 'month',
  },
  {
    id: 'price_plus_year',
    plan_id: 'plus',
    title: 'Plus Yearly',
    price_string: '$179.90/yr',
    interval: 'year',
  },
];

function renderSheet(overrides: { currentPeriodEnd?: number | null } = {}) {
  const currentPeriodEnd =
    'currentPeriodEnd' in overrides ? overrides.currentPeriodEnd : periodEnd;
  const onSubscriptionUpdate = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <PlansSheet
      open
      onOpenChange={onOpenChange}
      onSubscriptionUpdate={onSubscriptionUpdate}
      subscription={{
        plan: 'plus',
        status: 'active',
        is_unlimited: true,
        cancel_at_period_end: true,
        current_price_id: 'price_plus_month',
        current_period_end: currentPeriodEnd ?? undefined,
        features: [],
      }}
      cachedPlans={plans}
    />,
  );
  return { onSubscriptionUpdate, onOpenChange };
}

describe('PlansSheet pending cancellation', () => {
  beforeEach(() => {
    createCheckoutSession.mockReset();
    upgradeSubscription.mockReset();
  });

  it('shows the end date and confirms a resubscribe without closing', async () => {
    createCheckoutSession.mockResolvedValue({
      status: 'reactivated',
      next_billing_date: String(periodEnd),
    });
    const { onSubscriptionUpdate, onOpenChange } = renderSheet();

    expect(await screen.findByText(`Your Plus plan ends ${dateLabel}.`)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Resubscribe' }));

    await waitFor(() => {
      expect(createCheckoutSession).toHaveBeenCalledWith('price_plus_month');
    });
    expect(upgradeSubscription).not.toHaveBeenCalled();
    expect(
      await screen.findByText(`Your Plus plan will renew on ${dateLabel}.`),
    ).toBeTruthy();
    expect(screen.queryByText(`Your Plus plan ends ${dateLabel}.`)).toBeNull();
    expect(onSubscriptionUpdate).toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('does not invent an end date when the period end is missing', async () => {
    renderSheet({ currentPeriodEnd: null });
    expect(await screen.findByRole('button', { name: 'Resubscribe' })).toBeTruthy();
    expect(screen.queryByText(/Your Plus plan ends/)).toBeNull();
    expect(screen.queryByText(/No charge until/)).toBeNull();
    expect(screen.queryByText('—')).toBeNull();
  });

  it('refuses another price before any request', async () => {
    const { onOpenChange } = renderSheet();
    fireEvent.click(await screen.findByRole('button', { name: /Plus Yearly/ }));

    expect(await screen.findByText('Resubscribe first to change plans.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Resubscribe' }));

    await waitFor(() => {
      expect(
        screen.getAllByText('Resubscribe first to change plans.').length,
      ).toBeGreaterThan(0);
    });
    expect(createCheckoutSession).not.toHaveBeenCalled();
    expect(upgradeSubscription).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('surfaces a checkout 409 as an existing subscription, and any other checkout failure', async () => {
    createCheckoutSession.mockRejectedValueOnce(new Error('API error: 409 Conflict'));
    renderSheet();
    fireEvent.click(await screen.findByRole('button', { name: 'Resubscribe' }));
    expect(
      await screen.findByText(
        'You already have a subscription. Manage your existing subscription instead of starting a new checkout.',
      ),
    ).toBeTruthy();
    expect(screen.queryByText('Resubscribe first to change plans.')).toBeNull();

    createCheckoutSession.mockRejectedValueOnce(new Error('network down'));
    fireEvent.click(screen.getByRole('button', { name: 'Resubscribe' }));
    expect(await screen.findByText('An error occurred. Please try again.')).toBeTruthy();
  });
});
