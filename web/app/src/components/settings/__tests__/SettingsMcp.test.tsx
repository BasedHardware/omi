import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getDeveloperApiKeys: vi.fn(async () => []),
  getMcpApiKeys: vi.fn(async () => []),
  getDeveloperWebhooksStatus: vi.fn(async () => ({})),
  getDeveloperWebhook: vi.fn(async () => ({ url: '' })),
}));

import { SettingsPage } from '@/components/settings/SettingsPage';
import { hostedMcpConfigJson, hostedMcpUrl } from '@/lib/mcpConfig';

const store = new Map<string, string>();
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => void store.set(key, value),
  removeItem: (key: string) => void store.delete(key),
  clear: () => store.clear(),
});

describe('Settings > Developer > MCP', () => {
  beforeEach(() => {
    store.clear();
  });

  it('shows the canonical hosted MCP URL with the API base normalized', async () => {
    render(<SettingsPage />);
    // NEXT_PUBLIC_API_BASE_URL ends in a slash — the endpoint must join once.
    expect(
      (await screen.findAllByText('https://api.omi.me/v1/mcp')).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/\/v1\/mcp\/sse/)).toBeNull();
  });

  it('renders the hosted Streamable HTTP config as Claude Code ~/.claude.json, not the docker bridge', async () => {
    const { container } = render(<SettingsPage />);
    await screen.findAllByText('https://api.omi.me/v1/mcp');
    const expected = hostedMcpConfigJson(hostedMcpUrl('https://api.omi.me/'));
    // The rendered <pre> is the exact same string the Copy button writes.
    expect(container.querySelector('pre')?.textContent).toBe(expected);
    expect(expected).toContain('"type": "http"');
    expect(expected).not.toContain('docker');
    // The JSON snippet is labeled for Claude Code only — Claude Desktop uses
    // the Connectors flow, not a JSON file.
    expect(screen.getByText('Claude Code')).toBeTruthy();
    expect(screen.getByText('Add to ~/.claude.json')).toBeTruthy();
    expect(screen.queryByText('Add to claude_desktop_config.json')).toBeNull();
    expect(screen.queryByText(/claude_desktop_config/)).toBeNull();
  });

  it('shows the Claude Desktop Connectors OAuth flow separately', async () => {
    render(<SettingsPage />);
    await screen.findAllByText('https://api.omi.me/v1/mcp');
    expect(screen.getByText('Claude Desktop')).toBeTruthy();
    expect(
      screen.getAllByText(/Settings → Connectors → Add custom connector/).length,
    ).toBeGreaterThan(0);
  });

  it('explains the claude.ai OAuth connector flow with the prod client id', async () => {
    render(<SettingsPage />);
    await screen.findAllByText('https://api.omi.me/v1/mcp');
    expect(screen.getAllByText('omi-claude-prod').length).toBeGreaterThan(0);
    expect(
      screen.getByText(/never use your MCP API key as an\s*OAuth secret/i),
    ).toBeTruthy();
    expect(screen.getAllByText('Leave blank').length).toBeGreaterThan(0);
    expect(screen.queryByText('Use your MCP API key')).toBeNull();
  });
});
