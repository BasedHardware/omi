import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Memory } from '@/types/conversation';
import { MemoryList, MemoryListSkeleton } from '@/components/memories/MemoryList';

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: () => ({
    getVirtualItems: () => [],
    getTotalSize: () => 100,
    measureElement: vi.fn(),
    scrollToIndex: vi.fn(),
  }),
}));

const memory = {
  id: 'memory-1',
  content: 'Remember the full-height list.',
  created_at: '2026-08-11T00:00:00.000Z',
  updated_at: '2026-08-11T00:00:00.000Z',
  visibility: 'private',
} as Memory;

describe('MemoryList layout', () => {
  it('loads another page when filtering leaves the current page empty', async () => {
    const onLoadMore = vi.fn().mockResolvedValue(undefined);

    render(
      <MemoryList
        memories={[]}
        loading={false}
        hasMore
        onLoadMore={onLoadMore}
        onEdit={vi.fn().mockResolvedValue(true)}
        onDelete={vi.fn().mockResolvedValue(true)}
        onToggleVisibility={vi.fn().mockResolvedValue(true)}
      />,
    );

    await waitFor(() => expect(onLoadMore).toHaveBeenCalledOnce());
    expect(screen.queryByText('No memories yet')).not.toBeInTheDocument();
  });

  it('fills the remaining desktop height while retaining the mobile viewport cap', () => {
    render(
      <MemoryList
        memories={[memory]}
        loading={false}
        hasMore={false}
        onLoadMore={vi.fn().mockResolvedValue(undefined)}
        onEdit={vi.fn().mockResolvedValue(true)}
        onDelete={vi.fn().mockResolvedValue(true)}
        onToggleVisibility={vi.fn().mockResolvedValue(true)}
      />,
    );

    expect(screen.getByRole('region', { name: 'Memories list' })).toHaveClass(
      'max-h-[calc(100dvh-350px)]',
      'lg:max-h-none',
      'lg:flex-1',
      'lg:min-h-0',
      'pr-2',
      '[scrollbar-gutter:stable]',
      '[&::-webkit-scrollbar]:w-1.5',
    );
  });

  it('keeps skeleton shimmer still when reduced motion is preferred', () => {
    const { container } = render(<MemoryListSkeleton />);

    expect(container.firstElementChild?.firstElementChild).toHaveClass(
      'animate-pulse',
      'motion-reduce:animate-none',
    );
  });
});
