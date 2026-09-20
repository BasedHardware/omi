import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const { getTrainingDataOptIn, setTrainingDataOptIn } = vi.hoisted(() => ({
  getTrainingDataOptIn: vi.fn(async () => ({ opted_in: true })),
  setTrainingDataOptIn: vi.fn(async (_optIn: boolean) => {}),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('section=privacy'),
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
  getRecordingPermission: vi.fn(async () => ({ enabled: false })),
  getTrainingDataOptIn,
  setTrainingDataOptIn,
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

async function trainingDataToggle() {
  const label = await screen.findByText('Training Data');
  let row = label.parentElement;
  while (row && !row.querySelector('button')) row = row.parentElement;
  return within(row!).getByRole('button');
}

describe('Settings > Privacy > Training Data', () => {
  beforeEach(() => {
    getTrainingDataOptIn.mockClear();
    setTrainingDataOptIn.mockClear();
  });

  it('does not send another opt-in request when an opted-in user switches it off', async () => {
    render(<SettingsPage />);
    const toggle = await trainingDataToggle();
    await waitFor(() => expect(toggle.className).toContain('bg-text-primary'));

    fireEvent.click(toggle);

    expect(setTrainingDataOptIn).not.toHaveBeenCalled();
  });

  it('still sends the opt-in request when a user switches it on', async () => {
    getTrainingDataOptIn.mockResolvedValueOnce({ opted_in: false });
    render(<SettingsPage />);
    const toggle = await trainingDataToggle();
    await waitFor(() => expect(getTrainingDataOptIn).toHaveBeenCalled());

    fireEvent.click(toggle);

    await waitFor(() => expect(setTrainingDataOptIn).toHaveBeenCalledWith(true));
  });
});
