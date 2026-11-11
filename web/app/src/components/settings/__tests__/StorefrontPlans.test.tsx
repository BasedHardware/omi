import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { trackPurchaseEvent } from '@/lib/analytics/subscriptionFunnel';
import { parseStorefront, type PlanStorefront } from '@/lib/planStorefront';

const api = vi.hoisted(() => ({
  getStorefront: vi.fn(),
  createCheckoutSession: vi.fn(),
  upgradeSubscription: vi.fn(),
  getCustomerPortal: vi.fn(),
}));

vi.mock('@/lib/api', () => api);
vi.mock('@/lib/analytics/subscriptionFunnel', () => ({
  trackPurchaseEvent: vi.fn(),
  openPurchaseCheckout: vi.fn((url) => window.open(url, '_blank')),
  trackPaywallOpened: vi.fn(),
  trackUpgradePlanSelected: vi.fn(),
  trackUpgradeSucceeded: vi.fn(),
}));

import { StorefrontPlans } from '@/components/settings/storefront/StorefrontPlans';
import {
  BudgetUpsellBanner,
  StorefrontPanel,
} from '@/components/settings/storefront/StorefrontHost';

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  vi.mocked(trackPurchaseEvent).mockClear();
  vi.stubGlobal('open', vi.fn());
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const GOLDEN_DIR = resolve(process.cwd(), '../../backend/tests/fixtures/storefront_v2');
function golden(name: string): PlanStorefront {
  return parseStorefront(
    JSON.parse(readFileSync(resolve(GOLDEN_DIR, `${name}.json`), 'utf8')),
  );
}

function renderPlans(data: PlanStorefront, onSelect = vi.fn()) {
  render(
    <StorefrontPlans
      data={data}
      onRetry={vi.fn()}
      onSelect={onSelect}
      onManage={vi.fn()}
    />,
  );
  return onSelect;
}

describe('StorefrontPlans', () => {
  it('renders backend strings for Free and hides lower cards behind See all plans', () => {
    renderPlans(golden('free_settings'));
    expect(screen.getByText('Choose your plan')).toBeTruthy();
    expect(screen.getByText("You're on Free")).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Get Plus' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Get Pro' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'See all plans' }));
    expect(screen.getByRole('button', { name: 'Get Pro' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Get Architect' })).toBeTruthy();
  });

  it('yearly chip swaps to the yearly headline and price id', () => {
    const onSelect = renderPlans(golden('free_settings'));
    fireEvent.click(screen.getByRole('radio', { name: 'Yearly · 2 months free' }));
    const plus = screen.getByTestId('storefront-tier-plus');
    expect(within(plus).getByText('US$16.66/month')).toBeTruthy();
    fireEvent.click(within(plus).getByRole('button', { name: 'Get Plus' }));
    expect(onSelect.mock.calls[0][1].id).toBe('price_plus_year');
  });

  it('Pro at 100% leads with a recommended Architect checkout', () => {
    const onSelect = renderPlans(golden('pro_budget_cap'));
    const architect = screen.getByTestId('storefront-tier-architect');
    expect(within(architect).getByText('Recommended')).toBeTruthy();
    fireEvent.click(
      within(architect).getByRole('button', { name: 'Upgrade to Architect' }),
    );
    expect(onSelect.mock.calls[0][1].id).toBe('price_architect_month');
    expect(screen.getByTestId('storefront-usage-meter').textContent).toContain(
      '100% used',
    );
  });

  it('cancel-scheduled shows Resubscribe and the blocked line on every other card', () => {
    renderPlans(golden('cancel_scheduled_plus'));
    expect(screen.getByRole('button', { name: 'Resubscribe' })).toBeTruthy();
    expect(screen.queryByRole('radiogroup')).toBeNull();
    expect(screen.getAllByText('Resubscribe first to change plans')).toHaveLength(3);
    expect(screen.queryByText('Recommended')).toBeNull();
  });

  it('legacy shows the note and manage billing, never plan cards', () => {
    renderPlans(golden('legacy_neo'));
    expect(screen.getByTestId('storefront-legacy-note')).toBeTruthy();
    expect(screen.queryByTestId('storefront-tier-plus')).toBeNull();
    expect(screen.getByRole('button', { name: 'Manage billing' })).toBeTruthy();
  });

  it('renders nothing when the backend hides subscription UI', () => {
    const { container } = render(
      <StorefrontPlans
        data={{ ...golden('free_settings'), showSubscriptionUi: false }}
        onRetry={vi.fn()}
        onSelect={vi.fn()}
        onManage={vi.fn()}
      />,
    );
    expect(container.innerHTML).toBe('');
  });
});

describe('StorefrontPanel purchase routing', () => {
  it('same-tier annual requires backend confirmation before any billing call', async () => {
    api.getStorefront.mockResolvedValue(golden('plus_monthly_yearly_toggle'));
    api.upgradeSubscription.mockResolvedValue({ status: 'success' });
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    const label = 'Switch to yearly · save US$39.98';
    fireEvent.click(await screen.findByRole('button', { name: label }));
    expect(
      await screen.findByText('Your monthly plan continues until Nov 1'),
    ).toBeInTheDocument();
    expect(api.upgradeSubscription).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.upgradeSubscription).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: label }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: label }));
    await waitFor(() => expect(api.upgradeSubscription).toHaveBeenCalled());
  });

  it('Free starts Stripe Checkout with the payload price id', async () => {
    api.getStorefront.mockResolvedValue(golden('free_settings'));
    api.createCheckoutSession.mockResolvedValue({
      url: 'https://checkout.stripe.test/s',
    });
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Get Plus' }));
    await waitFor(() =>
      expect(api.createCheckoutSession).toHaveBeenCalledWith('price_plus_month'),
    );
    expect(api.upgradeSubscription).not.toHaveBeenCalled();
    expect(window.open).toHaveBeenCalledWith('https://checkout.stripe.test/s', '_blank');
    expect(api.getStorefront).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'web_plans', trigger: null }),
    );
  });

  it('a paid subscriber changes plan through upgrade-subscription', async () => {
    api.getStorefront.mockResolvedValue(golden('pro_budget_cap'));
    api.upgradeSubscription.mockResolvedValue({ status: 'success' });
    const onUpdate = vi.fn();
    render(
      <StorefrontPanel
        source="web_plans"
        trigger="usage_budget"
        onSubscriptionUpdate={onUpdate}
      />,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Upgrade to Architect' }));
    await waitFor(() =>
      expect(api.upgradeSubscription).toHaveBeenCalledWith('price_architect_month'),
    );
    expect(api.createCheckoutSession).not.toHaveBeenCalled();
    expect(onUpdate).toHaveBeenCalled();
  });

  it('resubscribe reactivates through checkout-session on the current price', async () => {
    api.getStorefront.mockResolvedValue(golden('cancel_scheduled_plus'));
    api.createCheckoutSession.mockResolvedValue({ status: 'reactivated' });
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Resubscribe' }));
    await waitFor(() =>
      expect(api.createCheckoutSession).toHaveBeenCalledWith('price_plus_month'),
    );
    expect(api.upgradeSubscription).not.toHaveBeenCalled();
  });

  it('a failed load shows retry and refetches', async () => {
    api.getStorefront
      .mockRejectedValueOnce(new Error('API error: 404'))
      .mockResolvedValue(golden('free_settings'));
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Get Plus' })).toBeTruthy();
  });
});

describe('BudgetUpsellBanner', () => {
  it('stays dark while the contextual gate is off', async () => {
    const readGate = vi.fn(async () => false);
    const { container } = render(
      <BudgetUpsellBanner readGate={readGate} onSubscriptionUpdate={vi.fn()} />,
    );
    await waitFor(() => expect(readGate).toHaveBeenCalled());
    expect(api.getStorefront).not.toHaveBeenCalled();
    expect(container.innerHTML).toBe('');
  });

  it('shows the 80% nudge with usage_budget and dismisses it for the period', async () => {
    api.getStorefront.mockResolvedValue(golden('plus_budget80'));
    render(
      <BudgetUpsellBanner readGate={async () => true} onSubscriptionUpdate={vi.fn()} />,
    );
    const nudge = golden('plus_budget80').usage.nudgeLine!;
    expect(await screen.findByText(nudge)).toBeTruthy();
    expect(api.getStorefront).toHaveBeenCalledWith(
      expect.objectContaining({ trigger: 'usage_budget' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(screen.queryByText(nudge)).toBeNull();
    expect(window.localStorage.getItem('omi.storefront.budgetNudgeDismissedPeriod')).toBe(
      '2026-10',
    );
  });

  it('at 100% opens the exhausted surface with the Architect upsell', async () => {
    api.getStorefront.mockResolvedValue(golden('pro_budget_cap'));
    render(
      <BudgetUpsellBanner readGate={async () => true} onSubscriptionUpdate={vi.fn()} />,
    );
    expect(await screen.findByText("You've used all of this month's usage")).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: 'See plans' }));
    expect(
      await screen.findByRole('button', { name: 'Upgrade to Architect' }),
    ).toBeTruthy();
  });
  it('a new buyer renders the single-plan Omi Pro sheet and checks it out, never a dead panel', async () => {
    // 2026-10-24 ruling: /v2/payments/plans answers a single unlimited_v2 tier
    // for a new buyer. The panel must render that card with a working CTA
    // (offLadder used to refuse unlimited_v2) and start checkout on it.
    api.getStorefront.mockResolvedValue(golden('single_plan_omi_pro'));
    api.createCheckoutSession.mockResolvedValue({
      url: 'https://checkout.stripe.test/pro',
    });
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    expect(await screen.findByText("You're on Free")).toBeTruthy();
    expect(screen.queryByText(/Couldn.t load plans/)).toBeNull();
    const card = screen.getByTestId('storefront-tier-unlimited_v2');
    fireEvent.click(within(card).getByRole('button', { name: 'Get Unlimited' }));
    await waitFor(() =>
      expect(api.createCheckoutSession).toHaveBeenCalledWith('price_omi_pro_month'),
    );
    expect(window.open).toHaveBeenCalledWith(
      'https://checkout.stripe.test/pro',
      '_blank',
    );
    // The yearly chip offers the annual Omi Pro price too.
    fireEvent.click(screen.getByRole('radio', { name: 'Yearly · 3 months free' }));
    fireEvent.click(within(card).getByRole('button', { name: 'Get Unlimited' }));
    await waitFor(() =>
      expect(api.createCheckoutSession).toHaveBeenCalledWith('price_omi_pro_year'),
    );
  });
});

const views = () =>
  vi.mocked(trackPurchaseEvent).mock.calls.filter(([id]) => id === 'paywallViewed');
describe('StorefrontPanel rendered purchase exposure', () => {
  it('waits through loading then counts once when selectable offers commit', async () => {
    let release!: (data: PlanStorefront) => void;
    api.getStorefront.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const tree = render(
      <StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />,
    );
    expect(views()).toHaveLength(0);
    release(golden('single_plan_omi_pro'));
    await screen.findByRole('button', { name: 'Get Unlimited' });
    await waitFor(() => expect(views()).toHaveLength(1));
    tree.rerender(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    expect(views()).toHaveLength(1);
  });
  it.each(['empty', 'hidden', 'legacy', 'blocked', 'invalid-price', 'unknown-live-plan'])(
    'no exposure for %s catalogs',
    (kind) => {
      let data = golden(kind === 'legacy' ? 'legacy_neo' : 'single_plan_omi_pro');
      if (kind === 'empty') data = { ...data, tiers: [] };
      if (kind === 'hidden') data = { ...data, showSubscriptionUi: false };
      if (kind === 'blocked')
        data = {
          ...data,
          tiers: data.tiers.map((tier) => ({ ...tier, blockedLine: 'Unavailable' })),
        };
      if (kind === 'invalid-price')
        data = {
          ...data,
          tiers: data.tiers.map((tier) => ({
            ...tier,
            prices: tier.prices.map((price) => ({ ...price, id: null })),
          })),
        };
      render(
        <StorefrontPanel
          source="web_plans"
          initial={data}
          livePlanId={kind === 'unknown-live-plan' ? 'future_plan' : undefined}
          onSubscriptionUpdate={vi.fn()}
        />,
      );
      expect(views()).toHaveLength(0);
    },
  );
  it('failed load does not consume exposure before retry returns offers', async () => {
    api.getStorefront
      .mockRejectedValueOnce(new Error('private'))
      .mockResolvedValue(golden('single_plan_omi_pro'));
    render(<StorefrontPanel source="web_plans" onSubscriptionUpdate={vi.fn()} />);
    const retry = await screen.findByRole('button', { name: 'Try again' });
    expect(views()).toHaveLength(0);
    fireEvent.click(retry);
    await screen.findByRole('button', { name: 'Get Unlimited' });
    await waitFor(() => expect(views()).toHaveLength(1));
  });
  it('collapsed purchasable tiers do not count until expanded; chip changes do not duplicate', async () => {
    const data = golden('single_plan_omi_pro');
    data.tiers = data.tiers.map((tier) => ({ ...tier, recommended: false }));
    render(
      <StorefrontPanel
        source="web_plans"
        initial={data}
        onSubscriptionUpdate={vi.fn()}
      />,
    );
    expect(views()).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'See all plans' }));
    await waitFor(() => expect(views()).toHaveLength(1));
    fireEvent.click(screen.getByRole('radio', { name: 'Yearly · 3 months free' }));
    fireEvent.click(screen.getByRole('button', { name: 'See all plans' }));
    fireEvent.click(screen.getByRole('button', { name: 'See all plans' }));
    expect(views()).toHaveLength(1);
  });
  it('only a price for the selected interval counts, then latches through interval changes', async () => {
    const data = golden('single_plan_omi_pro');
    data.tiers = data.tiers.map((tier) => ({
      ...tier,
      prices: tier.prices.map((price) => ({
        ...price,
        id: price.interval === 'month' ? null : price.id,
      })),
    }));
    render(
      <StorefrontPanel
        source="web_plans"
        initial={data}
        onSubscriptionUpdate={vi.fn()}
      />,
    );
    expect(views()).toHaveLength(0);
    fireEvent.click(screen.getByRole('radio', { name: 'Yearly · 3 months free' }));
    await waitFor(() => expect(views()).toHaveLength(1));
    fireEvent.click(screen.getByRole('radio', { name: 'Monthly' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Yearly · 3 months free' }));
    expect(views()).toHaveLength(1);
  });
});
