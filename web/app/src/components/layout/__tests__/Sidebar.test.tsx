import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import confetti from 'canvas-confetti';
import { Sidebar } from '@/components/layout/Sidebar';

let reducedMotion = false;

vi.mock('canvas-confetti', () => ({ default: vi.fn() }));
vi.mock('@tschk/moonshine-next/navigation', () => ({ usePathname: () => '/home' }));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children, ...props }: React.ComponentProps<'a'>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: ({ src, alt, className }: React.ComponentProps<'img'>) => (
    <img src={src} alt={alt} className={className} />
  ),
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { displayName: 'Omi User', email: 'user@example.com', photoURL: null },
    signOut: vi.fn(),
  }),
}));
vi.mock('@/components/notifications/NotificationContext', () => ({
  useNotificationContext: () => ({ toggleNotificationCenter: vi.fn(), unreadCount: 0 }),
}));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  reducedMotion = false;
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: reducedMotion,
      media: '(prefers-reduced-motion: reduce)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('collapsed desktop sidebar alignment', () => {
  it('centers destination and profile controls on the same rail axis', async () => {
    render(<Sidebar isOpen onClose={vi.fn()} />);

    const home = await screen.findByTitle('Home');
    const profile = await screen.findByTitle('Settings');

    expect(home).toHaveClass('px-[18px]');
    expect(profile).toHaveClass('h-12', 'justify-center', 'p-0');
    expect(profile.parentElement).toHaveClass('mx-2');
  });
});

describe('profile menu row shape', () => {
  it('matches every item radius to the outer menu container', async () => {
    localStorage.setItem('sidebar-expanded', 'true');
    render(<Sidebar isOpen onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /Omi User/ }));

    const items = [
      'Connectors',
      'Privacy',
      'Developer',
      'Account',
      'Download',
      'Help',
      'Feedback',
      'Discord',
      'Sign Out',
    ];

    for (const name of items) {
      expect(
        screen.getByRole(name === 'Sign Out' ? 'button' : 'link', { name }),
      ).toHaveClass('rounded-card');
    }
  });
});

describe('macOS promotion dismissal', () => {
  it('fires one neutral canvas explosion before dismissing permanently', async () => {
    localStorage.setItem('sidebar-expanded', 'true');
    render(<Sidebar isOpen onClose={vi.fn()} />);

    const dismiss = await screen.findByRole('button', { name: 'Dismiss' });
    expect(dismiss.closest('a')).toBeNull();
    fireEvent.click(dismiss);

    expect(confetti).toHaveBeenCalledTimes(1);
    expect(confetti).toHaveBeenCalledWith(
      expect.objectContaining({
        particleCount: 48,
        spread: 360,
        colors: ['#FFFFFF', '#E5E5E5', '#B0B0B0', '#888888'],
        disableForReducedMotion: true,
      }),
    );
    expect(localStorage.getItem('mobile-app-banner-dismissed')).toBe('true');
  });

  it('skips decorative particles when reduced motion is requested', async () => {
    reducedMotion = true;
    localStorage.setItem('sidebar-expanded', 'true');
    render(<Sidebar isOpen onClose={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Dismiss' })).toBeVisible(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(confetti).not.toHaveBeenCalled();
    expect(localStorage.getItem('mobile-app-banner-dismissed')).toBe('true');

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 430));
    });
  });
});
