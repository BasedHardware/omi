import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoriesPage } from '@/components/memories/MemoriesPage';

const mocks = vi.hoisted(() => ({
  loading: false,
  reducedMotion: false,
  hasMore: false,
  truncated: false,
  beliefEnabled: null as boolean | null,
  memoryView: 'useful_now' as 'useful_now' | 'history' | 'all',
  activeCategories: [] as string[],
  loadMore: vi.fn<() => Promise<void>>(),
  refresh: vi.fn<() => Promise<void>>(),
  setMemoryView: vi.fn(),
}));

vi.mock('framer-motion', async () => {
  const ReactModule = await import('react');
  const MotionDiv = ReactModule.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: { duration?: number };
    }
  >(
    (
      { initial: _initial, animate: _animate, exit: _exit, transition, ...props },
      ref,
    ) => <div ref={ref} data-motion-duration={transition?.duration} {...props} />,
  );

  return {
    AnimatePresence: ({
      children,
      mode,
    }: {
      children: React.ReactNode;
      mode?: string;
    }) => (
      <div data-testid={mode ? 'memory-list-presence' : undefined} data-mode={mode}>
        {children}
      </div>
    ),
    motion: { div: MotionDiv },
    useReducedMotion: () => mocks.reducedMotion,
  };
});

vi.mock('@/hooks/useMemories', () => ({
  useMemories: () => ({
    memories: [],
    loading: mocks.loading,
    error: null,
    hasMore: mocks.hasMore,
    truncated: mocks.truncated,
    beliefEnabled: mocks.beliefEnabled,
    memoryView: mocks.memoryView,
    setMemoryView: mocks.setMemoryView,
    loadMore: mocks.loadMore,
    refresh: mocks.refresh,
    addMemory: vi.fn(),
    editMemory: vi.fn(),
    removeMemory: vi.fn(),
    removeMemories: vi.fn(),
    toggleVisibility: vi.fn(),
    acceptMemory: vi.fn(),
    rejectMemory: vi.fn(),
    setCategories: vi.fn(),
    activeCategories: mocks.activeCategories,
  }),
}));

vi.mock('@/hooks/useInsightsDashboard', () => ({
  useInsightsDashboard: () => ({
    lifeBalance: [],
    risingTags: [],
    fadingTags: [],
  }),
}));

vi.mock('@/components/chat/ChatContext', () => ({
  useChat: () => ({ setContext: vi.fn() }),
}));

vi.mock('@/components/layout/PageToolbar', () => ({
  PageToolbar: ({ controls }: { controls?: React.ReactNode }) => (
    <div data-testid="memories-toolbar">{controls}</div>
  ),
}));

vi.mock('@/components/memories/MemoryQuickAdd', () => ({
  MemoryQuickAdd: () => <div data-testid="memory-quick-add" />,
}));

vi.mock('@/components/memories/MemoryList', () => ({
  MemoryList: ({ hasMore }: { hasMore: boolean }) => (
    <div data-testid="memory-list" data-has-more={hasMore} />
  ),
  MemoryListSkeleton: () => <div data-testid="memory-list-skeleton" />,
}));

describe('MemoriesPage list layout', () => {
  beforeEach(() => {
    mocks.loading = false;
    mocks.reducedMotion = false;
    mocks.hasMore = false;
    mocks.truncated = false;
    mocks.beliefEnabled = null;
    mocks.memoryView = 'useful_now';
    mocks.activeCategories = [];
    mocks.loadMore.mockReset();
    mocks.refresh.mockReset();
    mocks.setMemoryView.mockReset();
  });

  it('gives the desktop list column the remaining height without changing mobile flow', () => {
    render(<MemoriesPage />);

    expect(screen.getByTestId('memories-list-column')).toHaveClass(
      'flex-1',
      'min-h-0',
      'overflow-y-auto',
      'lg:overflow-hidden',
      'lg:flex',
      'lg:flex-col',
    );
    expect(screen.getByTestId('memory-list')).toBeInTheDocument();
  });

  it('crossfades the skeleton and content in the same layout cell', () => {
    mocks.loading = true;
    const { rerender } = render(<MemoriesPage />);

    expect(screen.getByTestId('memory-list-presence')).toHaveAttribute(
      'data-mode',
      'sync',
    );
    expect(screen.getByTestId('memory-list-transition')).toHaveClass('grid');
    expect(screen.getByTestId('memory-list-skeleton-state')).toHaveClass(
      'col-start-1',
      'row-start-1',
    );
    expect(screen.getByTestId('memory-list-skeleton-state')).toHaveAttribute(
      'data-motion-duration',
      '0.18',
    );

    mocks.loading = false;
    rerender(<MemoriesPage />);

    expect(screen.getByTestId('memory-list-content-state')).toHaveClass(
      'col-start-1',
      'row-start-1',
    );
    expect(screen.getByTestId('memory-list-content-state')).toHaveAttribute(
      'data-motion-duration',
      '0.18',
    );
  });

  it('shortens the opacity crossfade when reduced motion is preferred', () => {
    mocks.reducedMotion = true;
    render(<MemoriesPage />);

    expect(screen.getByTestId('memory-list-content-state')).toHaveAttribute(
      'data-motion-duration',
      '0.08',
    );
  });

  it('keeps pagination enabled while filtering categories client-side', () => {
    mocks.hasMore = true;
    mocks.activeCategories = ['system'];
    render(<MemoriesPage />);

    expect(screen.getByTestId('memory-list')).toHaveAttribute('data-has-more', 'true');
    expect(mocks.loadMore).not.toHaveBeenCalled();
  });

  it('exposes useful-now, history, and all only after the server advertises beta support', () => {
    mocks.beliefEnabled = true;
    render(<MemoriesPage />);

    expect(screen.getByRole('button', { name: 'Useful now' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'History' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'All' })).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'History' }));
    expect(mocks.setMemoryView).toHaveBeenCalledWith('history');
  });

  it('reports a bounded partial read instead of claiming the end of history', () => {
    mocks.beliefEnabled = true;
    mocks.truncated = true;
    render(<MemoriesPage />);

    expect(screen.getByRole('status')).toHaveTextContent('memory view is partial');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });
});
