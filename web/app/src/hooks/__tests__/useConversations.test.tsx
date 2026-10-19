import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAllCache, invalidateCache, invalidationPatterns } from '@/lib/cache';

vi.mock('@/lib/api', () => ({
  getConversations: vi.fn(),
}));

const { getConversations } = await import('@/lib/api');
const { useConversations } = await import('@/hooks/useConversations');

function page(offset: number, limit: number) {
  return Array.from({ length: limit }, (_, index) => {
    const n = offset + index;
    return {
      id: `c${n}`,
      created_at: new Date(Date.UTC(2026, 8, 1) - n * 60_000).toISOString(),
      status: 'completed',
    };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  clearAllCache();
  vi.mocked(getConversations).mockImplementation(
    async (params) => page(params?.offset ?? 0, params?.limit ?? 50) as never,
  );
});

describe('useConversations', () => {
  it('clears an earlier fetch error when a cached filter is shown', async () => {
    const { result, rerender } = renderHook(
      ({ folderId }: { folderId: string }) => useConversations({ limit: 50, folderId }),
      { initialProps: { folderId: 'home' } },
    );
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));

    // The next folder's first page fails, which shows the error banner.
    vi.mocked(getConversations).mockRejectedValueOnce(new Error('Network error'));
    rerender({ folderId: 'work' });
    await waitFor(() => expect(result.current.error).toBe('Network error'));

    // The first folder is still cached and fresh, so it comes back without a request.
    rerender({ folderId: 'home' });
    expect(result.current.conversations).toHaveLength(50);
    expect(getConversations).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });

  it('does not skip a page after the list is reloaded from the top', async () => {
    const { result } = renderHook(() => useConversations({ limit: 50 }));
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));

    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.conversations).toHaveLength(100);

    act(() => {
      invalidateCache(invalidationPatterns.conversations);
    });
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));

    await act(async () => {
      await result.current.loadMore();
    });

    expect(vi.mocked(getConversations).mock.calls.at(-1)![0]).toMatchObject({
      offset: 50,
    });
    expect(result.current.conversations.map((c) => c.id)).toContain('c50');
  });
});
