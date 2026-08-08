import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useParams: () => ({ id: 'missing-app' }),
}));
vi.mock('@/moonshine/register-client-route', () => ({
  registerMoonshineRoute: () => {},
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));
vi.mock('@/lib/api/public', () => ({
  findAppById: vi.fn(async () => null),
  getAppsV2: vi.fn(async () => ({
    groups: [],
    meta: { capabilities: [], groupCount: 0, limit: 20, offset: 0 },
  })),
  transformToPlugin: (raw: { capabilities?: string[] }) => ({
    ...raw,
    capabilities: new Set(raw.capabilities ?? []),
  }),
}));

import PluginDetailPage, { applyAppDetailMetadata } from '@/app/(public)/apps/[id]/page';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('app detail not-found', () => {
  it('renders an explicit not-found state instead of a blank page', async () => {
    const { getByTestId, getByText } = render(<PluginDetailPage />);
    await waitFor(() => expect(getByTestId('app-not-found')).toBeTruthy());
    expect(getByText('App not found')).toBeTruthy();
    expect(getByText('Browse the App Store').getAttribute('href')).toBe('/apps');
  });
});

describe('app detail metadata', () => {
  beforeEach(() => {
    document.head.innerHTML = '';
    document.title = '';
  });

  it('sets an app-specific title, canonical URL and social preview tags', () => {
    applyAppDetailMetadata({
      id: 'note-taker',
      name: 'Note Taker',
      description: 'Takes notes.',
      image: 'https://cdn.example.com/note.png',
    });

    expect(document.title).toBe('Note Taker — Omi App Store');
    const canonical = document.head.querySelector<HTMLLinkElement>(
      'link[rel="canonical"]',
    );
    expect(canonical?.href).toBe(`${window.location.origin}/apps/note-taker`);
    expect(
      document.head.querySelector('meta[property="og:title"]')?.getAttribute('content'),
    ).toBe('Note Taker');
    expect(
      document.head.querySelector('meta[property="og:image"]')?.getAttribute('content'),
    ).toBe('https://cdn.example.com/note.png');
    expect(
      document.head.querySelector('meta[name="description"]')?.getAttribute('content'),
    ).toBe('Takes notes.');
  });
});
