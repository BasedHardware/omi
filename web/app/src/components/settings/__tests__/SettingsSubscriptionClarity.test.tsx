import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  opened: vi.fn(),
  emptyPlans: false,

  selected: vi.fn(),
  succeeded: vi.fn(),
  upgrade: vi.fn(async () => ({ status: 'success' })),
  subscription: {
    plan: 'plus',
    status: 'active',
    is_unlimited: true,
    current_price_id: 'price_plus',
    transcription_seconds_limit: 90000,
    transcription_seconds_used: 45000,
  } as Record<string, unknown>,
}));
vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('section=account'),
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { uid: 'fixture', email: 'fixture@example.test', displayName: 'Fixture' },
    signOut: vi.fn(),
  }),
}));
vi.mock('@/lib/analytics/subscriptionFunnel', () => ({
  trackPaywallOpened: mocks.opened,
  trackUpgradePlanSelected: mocks.selected,
  trackUpgradeSucceeded: mocks.succeeded,
}));
vi.mock('@/lib/api', () => ({
  getUserLanguage: vi.fn(async () => 'en'),
  getCustomVocabulary: vi.fn(async () => []),
  getDailySummarySettings: vi.fn(async () => null),
  getAllUsageData: vi.fn(async () => null),
  getUserSubscription: vi.fn(async () => mocks.subscription),
  getAvailablePlans: vi.fn(async () => {
    return {
      plans: mocks.emptyPlans
        ? []
        : [
            {
              id: 'price_plus',
              plan_id: 'plus',
              title: 'Plus Monthly',
              interval: 'month',
              price_string: '$17.99/mo',
              is_active: true,
            },
            {
              id: 'price_unlimited',
              plan_id: 'unlimited_v2',
              title: 'Unlimited Annual',
              interval: 'year',
              price_string: '$22.49/mo',
            },
          ],
    };
  }),
  upgradeSubscription: mocks.upgrade,
}));
import { SettingsPage, UsageSectionContent } from '../SettingsPage';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.emptyPlans = false;
});

describe('Account billing keeps paid identity separate from the allowance', () => {
  it('shows Plus with its finite meter and records a real checkout selection', async () => {
    render(<SettingsPage />);
    expect(await screen.findByRole('heading', { name: 'Plus' })).toBeTruthy();
    expect(screen.getByText('12.5 h used of 25 h')).toBeTruthy();
    expect(screen.queryByText('Unlimited conversations')).toBeNull();
    // Finding the rendered heading does not await the paywall's passive effect.
    await waitFor(() =>
      expect(mocks.opened).toHaveBeenCalledExactlyOnceWith('usage_page', 'plus'),
    );
    fireEvent.click(screen.getByRole('button', { name: /Unlimited Annual/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Change Plan' }));
    await waitFor(() => expect(mocks.upgrade).toHaveBeenCalledWith('price_unlimited'));
    expect(mocks.selected).toHaveBeenCalledExactlyOnceWith(
      'unlimited_v2',
      'year',
      'usage_page',
    );
    await waitFor(() =>
      expect(mocks.succeeded).toHaveBeenCalledExactlyOnceWith('unlimited_v2', 'year'),
    );
  });

  it('does not record a paywall when prices load while usage is visible', async () => {
    const props: Parameters<typeof UsageSectionContent>[0] = {
      allUsage: null,
      subscription: { plan: 'plus', status: 'active' } as Parameters<
        typeof UsageSectionContent
      >[0]['subscription'],
      onSubscriptionUpdate: vi.fn(),
      cachedPlans: null,
    };
    const { rerender } = render(<UsageSectionContent {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Usage' }));
    const plans = [
      {
        id: 'price_plus',
        plan_id: 'plus',
        title: 'Plus Monthly',
        interval: 'month',
        price_string: '$17.99/mo',
      },
    ] as Parameters<typeof UsageSectionContent>[0]['cachedPlans'];
    rerender(<UsageSectionContent {...props} cachedPlans={plans} />);
    expect(mocks.opened).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Plan' }));
    await waitFor(() =>
      expect(mocks.opened).toHaveBeenCalledExactlyOnceWith('usage_page', 'plus'),
    );
  });
  it('does not record a paywall when no pricing choices are available', async () => {
    mocks.emptyPlans = true;
    mocks.subscription = { plan: 'plus', status: 'active' };
    render(<SettingsPage />);
    await screen.findByRole('heading', { name: 'Plus' });
    expect(mocks.opened).not.toHaveBeenCalled();
  });

  it('records the Basic paywall impression only when plan choices become visible', async () => {
    mocks.subscription = {
      plan: 'basic',
      status: 'active',
      is_unlimited: false,
      transcription_seconds_limit: 18000,
      transcription_seconds_used: 3600,
    };
    render(<SettingsPage />);
    // Account section mounted, but the plan grid is still behind "See plans".
    expect(await screen.findByRole('button', { name: 'See plans' })).toBeTruthy();
    expect(mocks.opened).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'See plans' }));
    await waitFor(() =>
      expect(mocks.opened).toHaveBeenCalledExactlyOnceWith('usage_page', 'basic'),
    );
  });
});
