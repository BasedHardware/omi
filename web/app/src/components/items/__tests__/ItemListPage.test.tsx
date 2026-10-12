import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const harness = vi.hoisted(() => ({ query: '' }));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(harness.query),
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock('@/lib/api', () => ({
  getConversation: vi.fn(),
  getActionItem: vi.fn(),
  findMemoriesByIds: vi.fn(),
}));

import { ItemListPage, type ItemListLoaders } from '@/components/items/ItemListPage';

function loaders(overrides: Partial<ItemListLoaders> = {}): ItemListLoaders {
  return {
    conversation: async (id) => (id === 'c-1' ? { title: 'Pricing sync' } : null),
    task: async (id) =>
      id === 't-1' ? { title: 'Send the deck', completed: false } : null,
    memories: async () => ({
      found: new Map([['m-1', { title: 'Prefers window seats' }]]),
      complete: true,
    }),
    ...overrides,
  };
}

describe('ItemListPage', () => {
  it('lists items in link order and links each to its closest view', async () => {
    harness.query = 'memory=m-1&conversation=c-1&x=y&task=t-1&conversation=gone';
    render(<ItemListPage loaders={loaders()} />);

    expect(screen.getByText('4 Items')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Send the deck')).toBeTruthy());

    const rows = screen.getByTestId('item-list').querySelectorAll('li');
    expect([...rows].map((row) => row.textContent)).toEqual([
      'MemoryPrefers window seats',
      'ConversationPricing sync',
      'TaskSend the deck',
      'ConversationNo longer available',
    ]);
    expect(screen.getByTestId('item-list-row-0').getAttribute('href')).toBe(
      '/memories?highlight=m-1',
    );
    expect(screen.getByTestId('item-list-row-1').getAttribute('href')).toBe(
      '/conversations?id=c-1',
    );
    expect(screen.getByTestId('item-list-row-2').getAttribute('href')).toBe(
      '/tasks?highlight=t-1',
    );
    expect(screen.getByTestId('item-list-unavailable-3').getAttribute('href')).toBeNull();
  });

  it('shows loading rows, and a failed lookup as unavailable rather than an error page', async () => {
    harness.query = 'task=t-1&memory=m-1';
    let finishMemories: (
      value: Awaited<ReturnType<ItemListLoaders['memories']>>,
    ) => void = () => {};
    render(
      <ItemListPage
        loaders={loaders({
          task: async () => {
            throw new Error('API error: 404');
          },
          memories: () =>
            new Promise((resolve) => {
              finishMemories = resolve;
            }),
        })}
      />,
    );
    expect(screen.getByTestId('item-list-loading-1')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId('item-list-unavailable-0')).toBeTruthy(),
    );

    // Not found in a partial walk: still linked, never claimed deleted.
    finishMemories({ found: new Map(), complete: false });
    await waitFor(() =>
      expect(screen.getByTestId('item-list-row-1').textContent).toContain(
        'Open in Memories',
      ),
    );
  });

  it('keeps a hidden memory unavailable when the index walk stopped early', async () => {
    harness.query = 'memory=m-archived';
    render(
      <ItemListPage
        loaders={loaders({
          memories: async () => ({
            found: new Map(),
            hidden: new Set(['m-archived']),
            complete: false,
          }),
        })}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('item-list-unavailable-0').textContent).toContain(
        'No longer available',
      ),
    );
    expect(screen.queryByText('Open in Memories')).toBeNull();
  });

  it('shows an empty state for a link with no recognised items', () => {
    harness.query = 'foo=bar';
    render(<ItemListPage loaders={loaders()} />);
    expect(screen.getByText('No Items')).toBeTruthy();
    expect(screen.getByTestId('item-list-empty')).toBeTruthy();
  });
});
