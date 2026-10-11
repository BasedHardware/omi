import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.omi.me/';
});

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
const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast }) }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getDeveloperApiKeys: vi.fn(async () => []),
  getMcpApiKeys: vi.fn(async () => []),
  getDeveloperWebhooksStatus: vi.fn(async () => ({})),
  getDeveloperWebhook: vi.fn(async () => ({ url: '' })),
  createDeveloperApiKey: vi.fn(),
  deleteDeveloperApiKey: vi.fn(),
  createMcpApiKey: vi.fn(),
  deleteMcpApiKey: vi.fn(),
}));

import { SettingsPage } from '@/components/settings/SettingsPage';
import {
  getDeveloperApiKeys,
  getMcpApiKeys,
  createDeveloperApiKey,
  deleteDeveloperApiKey,
  createMcpApiKey,
  deleteMcpApiKey,
} from '@/lib/api';

const store = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => void store.set(key, value),
  removeItem: (key: string) => void store.delete(key),
  clear: () => store.clear(),
});

const key = {
  id: 'key-1',
  name: 'My integration',
  key_prefix: 'masked',
  created_at: '2026-10-01',
  last_used_at: undefined,
};

describe('Settings key management', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getDeveloperApiKeys).mockResolvedValue([]);
    vi.mocked(getMcpApiKeys).mockResolvedValue([]);
  });

  it('shows genuine empty lists', async () => {
    render(<SettingsPage />);
    expect(await screen.findByText('No API keys created yet')).toBeTruthy();
    expect(screen.getByText('No MCP keys created yet')).toBeTruthy();
  });

  it.each([
    [
      'developer',
      getDeveloperApiKeys,
      'Failed to load API keys. Please try again.',
      'No API keys created yet',
    ],
    [
      'MCP',
      getMcpApiKeys,
      'Failed to load MCP keys. Please try again.',
      'No MCP keys created yet',
    ],
  ] as const)(
    'shows a %s list error and retries successfully',
    async (_kind, getKeys, message, empty) => {
      vi.mocked(getKeys).mockRejectedValueOnce(new Error('offline'));
      render(<SettingsPage />);
      const error = await screen.findByText(message);
      expect(screen.queryByText(empty)).toBeNull();
      fireEvent.click(
        within(error.closest('[role="alert"]')!).getByRole('button', { name: 'Retry' }),
      );
      expect(await screen.findByText(empty)).toBeTruthy();
      expect(getKeys).toHaveBeenCalledWith({ throwOnError: true });
      expect(getKeys).toHaveBeenCalledTimes(2);
    },
  );

  it.each([
    ['API', getDeveloperApiKeys, deleteDeveloperApiKey],
    ['MCP', getMcpApiKeys, deleteMcpApiKey],
  ] as const)(
    'keeps the %s key after a failed delete and shows an error',
    async (kind, getKeys, deleteKey) => {
      vi.mocked(getKeys).mockResolvedValue([key]);
      vi.mocked(deleteKey).mockRejectedValue(new Error('offline'));
      render(<SettingsPage />);
      fireEvent.click(
        await screen.findByRole('button', { name: `Delete ${kind} key My integration` }),
      );
      await waitFor(() =>
        expect(showToast).toHaveBeenCalledWith(
          `Failed to delete ${kind} key. Please try again.`,
          'error',
        ),
      );
      expect(screen.getByText('My integration')).toBeTruthy();
    },
  );

  it('requires permissions and includes goals in full access and read only', async () => {
    vi.mocked(createDeveloperApiKey).mockResolvedValue({ ...key, key: 'one-time-key' });
    render(<SettingsPage />);
    await screen.findByText('No API keys created yet');
    fireEvent.click(screen.getAllByRole('button', { name: 'Create Key' })[0]);
    fireEvent.change(screen.getByPlaceholderText('e.g., My App Integration'), {
      target: { value: 'My integration' },
    });
    const submit = screen.getAllByRole('button', { name: 'Create Key' }).at(-1)!;
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(createDeveloperApiKey).not.toHaveBeenCalled();
    const goals = screen.getByText('Goals').parentElement!;
    fireEvent.click(screen.getByRole('button', { name: 'Read Only' }));
    expect(
      within(goals).getByRole('button', { name: 'Goals read permission' }).className,
    ).toContain('bg-blue-500');
    fireEvent.click(screen.getByRole('button', { name: 'Full Access' }));
    fireEvent.click(submit);
    await waitFor(() =>
      expect(createDeveloperApiKey).toHaveBeenCalledWith('My integration', [
        'conversations:read',
        'conversations:write',
        'memories:read',
        'memories:write',
        'action_items:read',
        'action_items:write',
        'goals:read',
        'goals:write',
      ]),
    );
  });

  it.each([
    ['API', createDeveloperApiKey, 'e.g., My App Integration'],
    ['MCP', createMcpApiKey, 'e.g., Claude Code'],
  ] as const)('surfaces %s creation failures', async (kind, createKey, placeholder) => {
    vi.mocked(createKey).mockRejectedValue(new Error('offline'));
    render(<SettingsPage />);
    await screen.findByText('No API keys created yet');
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Create Key' })[kind === 'API' ? 0 : 1],
    );
    fireEvent.change(screen.getByPlaceholderText(placeholder), {
      target: { value: 'My integration' },
    });
    if (kind === 'API')
      fireEvent.click(screen.getByRole('button', { name: 'Full Access' }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Create Key' }).at(-1)!);
    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(
        `Failed to create ${kind} key. Please try again.`,
        'error',
      ),
    );
  });
});
