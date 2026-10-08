import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { WebhookSigningSecretStatusResponse } from '@/lib/omiApi.generated';

const api = vi.hoisted(() => ({
  getDeveloperWebhookSigningSecretStatus: vi.fn(
    async (): Promise<WebhookSigningSecretStatusResponse> => ({ configured: false }),
  ),
  issueDeveloperWebhookSigningSecret: vi.fn(async () => ({
    secret: 'whsec_brand-new-secret',
    created_at: '2026-10-08T12:00:00+00:00',
    previous_valid_until: null as string | null,
  })),
  deleteDeveloperWebhookSigningSecret: vi.fn(async () => {}),
  showToast: vi.fn(),
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
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ showToast: api.showToast }),
}));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getDeveloperApiKeys: vi.fn(async () => []),
  getMcpApiKeys: vi.fn(async () => []),
  getDeveloperWebhook: vi.fn(async () => ({ url: '' })),
  getDeveloperWebhooksStatus: vi.fn(async () => ({})),
  setDeveloperWebhook: vi.fn(async () => {}),
  enableDeveloperWebhook: vi.fn(async () => {}),
  disableDeveloperWebhook: vi.fn(async () => {}),
  getDeveloperWebhookSigningSecretStatus: api.getDeveloperWebhookSigningSecretStatus,
  issueDeveloperWebhookSigningSecret: api.issueDeveloperWebhookSigningSecret,
  deleteDeveloperWebhookSigningSecret: api.deleteDeveloperWebhookSigningSecret,
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

const store = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => void store.set(key, value),
  removeItem: (key: string) => void store.delete(key),
  clear: () => store.clear(),
});

const writeText = vi.fn(async () => {});
Object.assign(navigator, { clipboard: { writeText } });

describe('Settings > Developer > Signing secret', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getDeveloperWebhookSigningSecretStatus.mockResolvedValue({ configured: false });
  });

  it('shows the secret once after creating it and lets the developer copy it', async () => {
    render(<SettingsPage />);

    const create = await screen.findByRole('button', { name: /create secret/i });
    expect(screen.getByText(/deliveries carry no signature/i)).toBeInTheDocument();
    fireEvent.click(create);

    const dialog = await screen.findByRole('dialog', { name: /signing secret created/i });
    expect(within(dialog).getByText('whsec_brand-new-secret')).toBeInTheDocument();
    expect(api.issueDeveloperWebhookSigningSecret).toHaveBeenCalledTimes(1);

    fireEvent.click(within(dialog).getByRole('button', { name: /copy secret/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('whsec_brand-new-secret'));

    fireEvent.click(within(dialog).getByRole('button', { name: /done/i }));
    await waitFor(() =>
      expect(screen.queryByText('whsec_brand-new-secret')).not.toBeInTheDocument(),
    );

    // The row now reflects the configured state without ever re-reading the secret.
    expect(screen.getByRole('button', { name: /rotate/i })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /delete signing secret/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/signing since/i)).toBeInTheDocument();
  });

  it('rotates behind a confirmation and reports the previous secret window', async () => {
    api.getDeveloperWebhookSigningSecretStatus.mockResolvedValue({
      configured: true,
      created_at: '2026-10-01T12:00:00+00:00',
      previous_valid_until: null,
    });
    api.issueDeveloperWebhookSigningSecret.mockResolvedValue({
      secret: 'whsec_rotated-secret',
      created_at: '2026-10-08T12:00:00+00:00',
      previous_valid_until: '2099-10-09T12:00:00+00:00',
    });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: /rotate/i }));
    expect(api.issueDeveloperWebhookSigningSecret).not.toHaveBeenCalled();
    fireEvent.click(
      await screen.findByRole('button', { name: /^rotate$/i, hidden: false }),
    );

    const dialog = await screen.findByRole('dialog', { name: /signing secret rotated/i });
    expect(within(dialog).getByText('whsec_rotated-secret')).toBeInTheDocument();
    expect(
      within(dialog).getByText(/previous secret keeps working until/i),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: /done/i }));
    await waitFor(() =>
      expect(screen.getByText(/previous secret valid until/i)).toBeInTheDocument(),
    );
  });

  it('deletes behind a confirmation and returns to the unsigned state', async () => {
    api.getDeveloperWebhookSigningSecretStatus.mockResolvedValue({
      configured: true,
      created_at: '2026-10-01T12:00:00+00:00',
      previous_valid_until: null,
    });
    render(<SettingsPage />);

    fireEvent.click(
      await screen.findByRole('button', { name: /delete signing secret/i }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }));

    await waitFor(() =>
      expect(api.deleteDeveloperWebhookSigningSecret).toHaveBeenCalledTimes(1),
    );
    expect(
      await screen.findByRole('button', { name: /create secret/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/deliveries carry no signature/i)).toBeInTheDocument();
  });

  it('keeps the row usable and toasts when creating fails', async () => {
    api.issueDeveloperWebhookSigningSecret.mockRejectedValue(new Error('API error: 500'));
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: /create secret/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not create the secret/i,
    );
    expect(api.showToast).toHaveBeenCalledWith(
      expect.stringMatching(/signing secret/i),
      'error',
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create secret/i })).toBeEnabled();
  });

  it('offers a retry when the status cannot be loaded', async () => {
    api.getDeveloperWebhookSigningSecretStatus
      .mockRejectedValueOnce(new Error('API error: 503'))
      .mockResolvedValueOnce({ configured: false });
    render(<SettingsPage />);

    expect(
      await screen.findByText(/could not load the signing status/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(
      await screen.findByRole('button', { name: /create secret/i }),
    ).toBeInTheDocument();
  });
});
