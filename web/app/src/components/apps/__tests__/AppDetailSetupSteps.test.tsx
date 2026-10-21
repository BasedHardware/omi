import { render, screen } from '@testing-library/react';
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
vi.mock('@/lib/api', () => ({
  getApp: vi.fn(async () => ({
    id: 'app-1',
    name: 'Notion Sync',
    description: 'Syncs notes',
    image: 'https://ex.com/logo.png',
    author: 'Dev',
    uid: 'owner-1',
    category: 'productivity-and-organization',
    capabilities: ['external_integration'],
    enabled: false,
    external_integration: {
      triggers_on: 'memory_creation',
      auth_steps: [{ name: 'Connect Notion', url: 'https://ex.com/connect?source=omi' }],
    },
  })),
  enableApp: vi.fn(),
  disableApp: vi.fn(),
  reEnableApp: vi.fn(),
}));

import { AppDetail } from '@/components/apps/AppDetail';

describe('AppDetail setup steps', () => {
  it('links each setup step with the signed-in uid', async () => {
    render(<AppDetail appId="app-1" />);

    const link = (await screen.findByText('Connect Notion')).closest('a')!;

    expect(link.getAttribute('href')).toBe(
      'https://ex.com/connect?source=omi&uid=user-1',
    );
  });
});
