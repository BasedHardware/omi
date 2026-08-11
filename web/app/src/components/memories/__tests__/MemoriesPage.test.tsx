import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoriesPage } from '@/components/memories/MemoriesPage';

vi.mock('@/hooks/useMemories', () => ({
  useMemories: () => ({
    memories: [],
    loading: false,
    error: null,
    hasMore: false,
    loadMore: vi.fn(),
    addMemory: vi.fn(),
    editMemory: vi.fn(),
    removeMemory: vi.fn(),
    removeMemories: vi.fn(),
    toggleVisibility: vi.fn(),
    acceptMemory: vi.fn(),
    rejectMemory: vi.fn(),
    setCategories: vi.fn(),
    activeCategories: [],
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
  PageToolbar: () => <div data-testid="memories-toolbar" />,
}));

vi.mock('@/components/memories/MemoryQuickAdd', () => ({
  MemoryQuickAdd: () => <div data-testid="memory-quick-add" />,
}));

vi.mock('@/components/memories/MemoryList', () => ({
  MemoryList: () => <div data-testid="memory-list" />,
  MemoryListSkeleton: () => <div data-testid="memory-list-skeleton" />,
}));

describe('MemoriesPage list layout', () => {
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
});
