import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
        auth_steps: [],
      },
    };
  }),
  enableApp: vi.fn(),
  disableApp: vi.fn(),
  reEnableApp: vi.fn(),
}));

import { AppDetail } from '@/components/apps/AppDetail';

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
});
