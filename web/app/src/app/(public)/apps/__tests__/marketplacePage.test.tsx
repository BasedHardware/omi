import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getAppsV2: vi.fn(),
  getAllAppsV2: vi.fn(),
}));

vi.mock('@/lib/api/public', () => ({
  getAppsV2: api.getAppsV2,
  getAllAppsV2: api.getAllAppsV2,
  transformToPlugin: (app: Record<string, unknown>) => ({
    ...app,
    capabilities: new Set(),
  }),
}));
vi.mock('@/components/marketplace/AppList', () => ({
  default: ({
    initialPlugins,
  }: {
    initialPlugins: Array<{ id: string; name: string }>;
  }) => (
    <div>
      {initialPlugins.map((plugin) => (
        <span key={plugin.id}>{plugin.name}</span>
      ))}
    </div>
  ),
}));
vi.mock('@/components/marketplace/PromoCard', () => ({ PromoCard: () => null }));
vi.mock('@/components/seo/JsonLd', () => ({ CollectionPageJsonLd: () => null }));
vi.mock('@/moonshine/register-client-route', () => ({
  registerMoonshineRoute: () => {},
}));

import AppsMarketplacePage from '@/app/(public)/apps/page';

describe('apps marketplace background loading', () => {
  it('keeps the initial catalogue when the full catalogue request fails empty', async () => {
    api.getAppsV2.mockResolvedValue({
      groups: [
        {
          data: [{ id: 'initial-app', name: 'Initial App' }],
        },
      ],
    });
    api.getAllAppsV2.mockResolvedValue([]);

    const { getByText } = render(<AppsMarketplacePage />);

    await waitFor(() => expect(api.getAllAppsV2).toHaveBeenCalledOnce());
    expect(getByText('Initial App')).toBeTruthy();
  });
});
