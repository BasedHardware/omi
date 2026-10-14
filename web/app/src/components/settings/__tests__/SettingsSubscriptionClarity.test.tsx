import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  opened: vi.fn(),
  selected: vi.fn(),
  succeeded: vi.fn(),
  upgrade: vi.fn(async () => ({ status: 'success' })),
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
  getUserSubscription: vi.fn(async () => ({
    plan: 'plus',
    status: 'active',
    is_unlimited: true,
    current_price_id: 'price_plus',
    transcription_seconds_limit: 90000,
    transcription_seconds_used: 45000,
  })),
  getAvailablePlans: vi.fn(async () => ({
    plans: [
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
  })),
  upgradeSubscription: mocks.upgrade,
}));
import { SettingsPage } from '../SettingsPage';

beforeEach(() => vi.clearAllMocks());

describe('Account billing keeps paid identity separate from the allowance', () => {
  it('shows Plus with its finite meter and records a real checkout selection', async () => {
    render(<SettingsPage />);
    expect(await screen.findByRole('heading', { name: 'Plus' })).toBeTruthy();
    expect(screen.getByText('12.5 h used of 25 h')).toBeTruthy();
    expect(screen.queryByText('Unlimited conversations')).toBeNull();
    expect(mocks.opened).toHaveBeenCalledExactlyOnceWith('usage_page', 'plus');
    fireEvent.click(screen.getByRole('button', { name: /Unlimited Annual/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Change Plan' }));
    await waitFor(() => expect(mocks.upgrade).toHaveBeenCalledWith('price_unlimited'));
    expect(mocks.selected).toHaveBeenCalledExactlyOnceWith(
      'unlimited_v2',
      'year',
      'usage_page',
    );
    expect(mocks.succeeded).toHaveBeenCalledExactlyOnceWith('unlimited_v2', 'year');
  });
});
