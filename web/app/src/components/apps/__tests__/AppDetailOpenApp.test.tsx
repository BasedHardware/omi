import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
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
  useAuth: () => ({ user: { uid: 'user-1' } }),
}));

let grant = 0;
vi.mock('@/lib/api', () => ({
  getApp: vi.fn(async () => {
    grant += 1;
    return {
      id: 'app-1',
      name: 'pCloud Backup',
      description: 'Backs up conversations',
      image: 'https://ex.com/logo.png',
      author: 'Dev',
      uid: 'owner-1',
      category: 'utilities',
      capabilities: ['external_integration'],
      enabled: true,
      external_integration: {
        triggers_on: 'memory_creation',
        app_home_url: `https://ex.com/home?grant=${grant}`,
        auth_steps: [
          {
            name: 'Connect pCloud',
            url: `https://ex.com/setup?uid=user-1&omi_token=signed.${grant}`,
          },
        ],
      },
    };
  }),
  enableApp: vi.fn(),
  disableApp: vi.fn(),
  reEnableApp: vi.fn(),
}));

import { AppDetail } from '@/components/apps/AppDetail';
import { getApp } from '@/lib/api';

beforeEach(() => {
  grant = 0;
  vi.clearAllMocks();
});
afterEach(cleanup);

describe('AppDetail Open App', () => {
  it('opens a freshly fetched launch grant on each click', async () => {
    const tabs: { opener: unknown; location: { href: string }; close: () => void }[] = [];
    vi.spyOn(window, 'open').mockImplementation(() => {
      const tab = { opener: window, location: { href: '' }, close: vi.fn() };
      tabs.push(tab);
      return tab as unknown as Window;
    });
    render(<AppDetail appId="app-1" />);

    const button = await screen.findByRole('button', { name: /Open App/ });
    fireEvent.click(button);
    await waitFor(() =>
      expect(tabs[0]?.location.href).toBe('https://ex.com/home?grant=2'),
    );
    fireEvent.click(button);
    await waitFor(() =>
      expect(tabs[1]?.location.href).toBe('https://ex.com/home?grant=3'),
    );
    expect(tabs[0].opener).toBeNull();
  });

  it('refreshes each setup click and preserves the signed query', async () => {
    const tab = { opener: window, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    render(<AppDetail appId="app-1" />);
    const setup = await screen.findByRole('button', { name: /Connect pCloud/ });
    fireEvent.click(setup);
    await waitFor(() =>
      expect(tab.location.href).toBe(
        'https://ex.com/setup?omi_token=signed.2&uid=user-1',
      ),
    );
    fireEvent.click(setup);
    await waitFor(() =>
      expect(tab.location.href).toBe(
        'https://ex.com/setup?omi_token=signed.3&uid=user-1',
      ),
    );
    expect(tab.opener).toBeNull();
  });

  it('closes the reserved tab on refresh failure instead of opening a cached grant', async () => {
    const tab = { opener: window, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    render(<AppDetail appId="app-1" />);
    const setup = await screen.findByRole('button', { name: /Connect pCloud/ });
    vi.mocked(getApp).mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(setup);
    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(tab.location.href).toBe('');
    expect(screen.getByRole('alert').textContent).toMatch(/Try again/);
  });

  it('does not navigate a late launch after leaving the app detail', async () => {
    const tab = { opener: window, location: { href: '' }, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    const { unmount } = render(<AppDetail appId="app-1" />);
    const setup = await screen.findByRole('button', { name: /Connect pCloud/ });
    const fresh = await getApp('app-1');
    let finish!: (value: typeof fresh) => void;
    vi.mocked(getApp).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(setup);
    unmount();
    finish(fresh);
    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(tab.location.href).toBe('');
  });
});
