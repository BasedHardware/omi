import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  checkout: vi.fn(async (_priceId: string) => ({
    url: 'https://checkout.stripe.test/pay',
  })),
  track: vi.fn(),
}));
vi.mock('@/lib/api', () => ({ createCheckoutSession: mocks.checkout }));
vi.mock('@/lib/analytics/posthog', () => ({ PostHogManager: { track: mocks.track } }));
vi.mock('@/lib/planStorefrontGate', () => ({
  PlanStorefrontGate: { sheetEnabled: async () => false },
}));
vi.mock('@/components/auth/AuthProvider', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@tschk/moonshine-next/image', () => ({ default: () => null }));
vi.mock('@tschk/moonshine-next/link', () => ({ default: () => null }));

import { UsageSectionContent } from '@/components/settings/SettingsPage';
import { CHECKOUT_POPUP_BLOCKED } from '@/lib/checkoutWindow';

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe('SettingsPage checkout', () => {
  it('shows blocked guidance, retries the same annual offer and tracks each actual launch result once', async () => {
    const checkout = { opener: window };
    vi.stubGlobal(
      'open',
      vi
        .fn()
        .mockReturnValueOnce(null)
        .mockReturnValueOnce(null)
        .mockReturnValue(checkout),
    );
    const onUpdate = vi.fn();
    render(
      <UsageSectionContent
        subscription={{ plan: 'basic', status: 'active', is_unlimited: false }}
        allUsage={null}
        onSubscriptionUpdate={onUpdate}
        cachedPlans={[
          {
            id: 'fixture_pro_month',
            plan_id: 'unlimited_v2',
            title: 'Omi Pro Monthly',
            interval: 'month',
            price_string: '$29.99/mo',
          },
          {
            id: 'fixture_pro_year',
            plan_id: 'unlimited_v2',
            title: 'Omi Pro Annual',
            interval: 'year',
            price_string: '$22.49/mo',
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'See plans' }));
    fireEvent.click(await screen.findByRole('button', { name: /Omi Pro Annual/ }));
    const cta = screen.getByRole('button', { name: 'Continue to Payment' });
    const selections = () =>
      mocks.track.mock.calls.filter(([name]) => name === 'Upgrade Plan Selected');
    for (let click = 1; click <= 2; click++) {
      fireEvent.click(cta);
      expect(await screen.findByText(CHECKOUT_POPUP_BLOCKED)).toBeInTheDocument();
      expect(cta).toBeEnabled();
      expect(selections()).toHaveLength(click);
      expect(selections()[click - 1]).toEqual([
        'Upgrade Plan Selected',
        {
          plan: 'unlimited_v2',
          billing_interval: 'year',
          source: 'usage_page',
          launch_result: 'blocked',
        },
      ]);
      fireEvent.focus(window);
      expect(onUpdate).not.toHaveBeenCalled();
    }
    fireEvent.click(cta);
    await waitFor(() => expect(selections()).toHaveLength(3));
    expect(selections()[2]).toEqual([
      'Upgrade Plan Selected',
      {
        plan: 'unlimited_v2',
        billing_interval: 'year',
        source: 'usage_page',
        launch_result: 'opened',
      },
    ]);
    expect(mocks.checkout.mock.calls).toEqual([
      ['fixture_pro_year'],
      ['fixture_pro_year'],
      ['fixture_pro_year'],
    ]);
    expect(screen.queryByText(CHECKOUT_POPUP_BLOCKED)).toBeNull();
    expect(checkout.opener).toBeNull();
    fireEvent.focus(window);
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });
});
