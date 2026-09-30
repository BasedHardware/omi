import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { getDeveloperWebhook, getDeveloperWebhooksStatus, setDeveloperWebhook } =
  vi.hoisted(() => ({
    getDeveloperWebhook: vi.fn(async (type: string) =>
      type === 'audio_bytes' ? { url: 'https://hooks.test/audio,30' } : { url: '' },
    ),
    getDeveloperWebhooksStatus: vi.fn(async () => ({ audio_bytes: true })),
    setDeveloperWebhook: vi.fn(async (_type: string, _url: string) => {}),
  }));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('section=developer'),
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
  getDeveloperApiKeys: vi.fn(async () => []),
  getMcpApiKeys: vi.fn(async () => []),
  getDeveloperWebhook,
  getDeveloperWebhooksStatus,
  setDeveloperWebhook,
  enableDeveloperWebhook: vi.fn(async () => {}),
  disableDeveloperWebhook: vi.fn(async () => {}),
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

// The developer section touches localStorage while loading; this runner does not
// always provide one.
const store = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => void store.set(key, value),
  removeItem: (key: string) => void store.delete(key),
  clear: () => store.clear(),
});

const interval = () =>
  screen.getByPlaceholderText('Interval (seconds)') as HTMLInputElement;

describe('Settings > Developer > Audio Bytes webhook', () => {
  beforeEach(() => {
    setDeveloperWebhook.mockClear();
  });

  it('keeps the saved interval after saving it', async () => {
    render(<SettingsPage />);

    await waitFor(() => expect(interval().value).toBe('30'));
    await act(async () => {
      fireEvent.blur(interval());
    });

    expect(setDeveloperWebhook).toHaveBeenCalledWith(
      'audio_bytes',
      'https://hooks.test/audio,30',
    );
    expect(interval().value).toBe('30');
  });

  it('sends the saved interval again when the url is edited afterwards', async () => {
    render(<SettingsPage />);

    await waitFor(() => expect(interval().value).toBe('30'));
    await act(async () => {
      fireEvent.blur(interval());
    });
    setDeveloperWebhook.mockClear();

    await act(async () => {
      fireEvent.blur(screen.getByPlaceholderText('https://your-server.com/webhook'));
    });

    expect(setDeveloperWebhook).toHaveBeenCalledWith(
      'audio_bytes',
      'https://hooks.test/audio,30',
    );
  });
});
