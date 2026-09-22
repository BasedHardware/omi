import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const { getDailySummarySettings, updateDailySummarySettings } = vi.hoisted(() => ({
  getDailySummarySettings: vi.fn(async () => ({ enabled: true, hour: 7 })),
  updateDailySummarySettings: vi.fn(
    async (_settings: { enabled: boolean; hour: number }) => {},
  ),
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
    user: { uid: 'user-1', email: 'user@example.com', displayName: 'User' },
    signOut: vi.fn(),
  }),
}));
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getDailySummarySettings,
  updateDailySummarySettings,
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

async function clickDailySummaryToggle() {
  const label = await screen.findByText('Daily Summary');
  await waitFor(() => expect(getDailySummarySettings).toHaveBeenCalled());
  let row = label.parentElement;
  while (row && !row.querySelector('button')) row = row.parentElement;
  fireEvent.click(within(row!).getByRole('button'));
}

describe('Settings > Account > Daily Summary', () => {
  beforeEach(() => {
    getDailySummarySettings.mockClear();
    updateDailySummarySettings.mockClear();
  });

  it('does not save the settings when the load failed', async () => {
    getDailySummarySettings.mockRejectedValueOnce(new Error('offline'));
    render(<SettingsPage />);

    await clickDailySummaryToggle();

    expect(updateDailySummarySettings).not.toHaveBeenCalled();
  });

  it('keeps the delivery time the user had when toggling it off', async () => {
    getDailySummarySettings.mockResolvedValueOnce({ enabled: true, hour: 7 });
    render(<SettingsPage />);

    await clickDailySummaryToggle();

    await waitFor(() =>
      expect(updateDailySummarySettings).toHaveBeenCalledWith({
        enabled: false,
        hour: 7,
      }),
    );
  });
});
