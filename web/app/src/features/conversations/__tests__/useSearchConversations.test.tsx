import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation } from '@/types/conversation';

vi.mock('@/features/conversations/api', () => ({
  searchConversations: vi.fn(),
}));

const api = await import('@/features/conversations/api');
const { useSearchConversations } = await import(
  '@/features/conversations/useSearchConversations'
);

function conversation(id: string): Conversation {
  return {
    id,
    created_at: '2026-01-01T00:00:00Z',
    started_at: '2026-01-01T00:00:00Z',
    structured: { title: id, overview: '', emoji: '', category: 'other' },
  } as unknown as Conversation;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('useSearchConversations', () => {
  it('replaces results on a new search', async () => {
    vi.mocked(api.searchConversations).mockResolvedValue({
      items: [conversation('c1')],
      current_page: 1,
      total_pages: 2,
    });

    const { result } = renderHook(() => useSearchConversations());

    await act(async () => {
      await result.current.search('hello');
    });

    expect(result.current.results.map((entry) => entry.id)).toEqual(['c1']);
    expect(result.current.totalPages).toBe(2);
  });

  it('appends the next page using peek rather than a stale loading flag', async () => {
    vi.mocked(api.searchConversations)
      .mockResolvedValueOnce({
        items: [conversation('c1')],
        current_page: 1,
        total_pages: 2,
      })
      .mockResolvedValueOnce({
        items: [conversation('c2')],
        current_page: 2,
        total_pages: 2,
      });

    const { result } = renderHook(() => useSearchConversations());

    await act(async () => {
      await result.current.search('hello');
    });
    await act(async () => {
      await result.current.loadMore();
    });

    expect(result.current.results.map((entry) => entry.id)).toEqual(['c1', 'c2']);
    expect(result.current.currentPage).toBe(2);
  });

  it('clears without calling search', async () => {
    vi.mocked(api.searchConversations).mockResolvedValue({
      items: [conversation('c1')],
      current_page: 1,
      total_pages: 1,
    });
    const { result } = renderHook(() => useSearchConversations());
    await act(async () => {
      await result.current.search('hello');
    });

    act(() => {
      result.current.clear();
    });

    expect(result.current.results).toEqual([]);
    expect(result.current.currentPage).toBe(1);
  });
});
