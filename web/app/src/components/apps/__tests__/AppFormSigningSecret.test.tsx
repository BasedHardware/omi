import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppForm } from '@/components/apps/AppForm';
import type { App } from '@/types/apps';
import type { WebhookSigningSecretStatusResponse } from '@/lib/omiApi.generated';

const api = vi.hoisted(() => ({
  getAppCategories: vi.fn(async () => [{ id: 'productivity', title: 'Productivity' }]),
  getAppCapabilities: vi.fn(async () => [
    { id: 'external_integration', title: 'External Integration' },
  ]),
  getNotificationScopes: vi.fn(async () => []),
  getPaymentPlans: vi.fn(async () => []),
  createApp: vi.fn(async () => ({ app_id: 'app-2' })),
  updateApp: vi.fn(async () => {}),
  uploadAppThumbnail: vi.fn(async () => ({ thumbnail_url: '', thumbnail_id: '' })),
  generateAppDescription: vi.fn(async () => ''),
  deleteApp: vi.fn(async () => {}),
  getAppWebhookSigningSecretStatus: vi.fn(
    async (_appId: string): Promise<WebhookSigningSecretStatusResponse> => ({
      configured: false,
    }),
  ),
  issueAppWebhookSigningSecret: vi.fn(async (_appId: string) => ({
    secret: 'whsec_app-secret',
    created_at: '2026-10-08T12:00:00+00:00',
    previous_valid_until: null as string | null,
  })),
  deleteAppWebhookSigningSecret: vi.fn(async (_appId: string) => {}),
}));

vi.mock('@/lib/api', () => api);
vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));

const app = {
  id: 'app-1',
  name: 'Slack bridge',
  description: 'Posts conversations to Slack',
  category: 'productivity',
  capabilities: ['external_integration'],
  external_integration: {
    triggers_on: 'memory_creation',
    webhook_url: 'https://bridge.test/hook',
  },
  private: false,
} as unknown as App;

describe('AppForm > External Integration > Webhook signing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAppWebhookSigningSecretStatus.mockResolvedValue({ configured: false });
  });

  it('loads the app status in edit mode and creates a secret without submitting the form', async () => {
    render(<AppForm mode="edit" app={app} />);

    await waitFor(() =>
      expect(api.getAppWebhookSigningSecretStatus).toHaveBeenCalledWith('app-1'),
    );
    expect(
      screen.getByText(/this secret also signs your app's chat-tool calls/i),
    ).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /create secret/i }));

    const dialog = await screen.findByRole('dialog', { name: /signing secret created/i });
    expect(within(dialog).getByText('whsec_app-secret')).toBeInTheDocument();
    expect(api.issueAppWebhookSigningSecret).toHaveBeenCalledWith('app-1');
    expect(api.updateApp).not.toHaveBeenCalled();
  });

  it('deletes the app secret behind a confirmation', async () => {
    api.getAppWebhookSigningSecretStatus.mockResolvedValue({
      configured: true,
      created_at: '2026-10-01T12:00:00+00:00',
      previous_valid_until: null,
    });
    render(<AppForm mode="edit" app={app} />);

    fireEvent.click(
      await screen.findByRole('button', { name: /delete signing secret/i }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }));

    await waitFor(() =>
      expect(api.deleteAppWebhookSigningSecret).toHaveBeenCalledWith('app-1'),
    );
    expect(
      await screen.findByRole('button', { name: /create secret/i }),
    ).toBeInTheDocument();
  });

  it('explains that the secret comes after creation in create mode and never calls the API', async () => {
    render(<AppForm mode="create" />);

    fireEvent.click(await screen.findByRole('button', { name: /external integration/i }));

    expect(
      await screen.findByText(/available after the app is created/i),
    ).toBeInTheDocument();
    expect(api.getAppWebhookSigningSecretStatus).not.toHaveBeenCalled();
  });
});
