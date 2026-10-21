import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { invalidateCache, invalidationPatterns } from '@/lib/cache';

vi.mock('@/lib/api', () => ({
  getActionItems: vi.fn(),
  createActionItem: vi.fn(),
  toggleActionItemCompleted: vi.fn(),
  updateActionItemDueDate: vi.fn(),
  updateActionItemDescription: vi.fn(),
  deleteActionItem: vi.fn(),
}));

const { getActionItems, deleteActionItem } = await import('@/lib/api');
const { useActionItems } = await import('@/hooks/useActionItems');

function item(id: string) {
  return { id, description: id, completed: false, created_at: '2026-01-01T00:00:00Z' };
}

beforeEach(() => {
  // Reset, not just clear: tests install implementations that must not leak.
  vi.resetAllMocks();
});

describe('useActionItems', () => {
  it('keeps the loaded list visible while a cache-invalidation refetch is in flight', async () => {
    let resolveRefresh: (value: {
      items: ReturnType<typeof item>[];
      hasMore: boolean;
    }) => void = () => undefined;

    vi.mocked(getActionItems)
      .mockResolvedValueOnce({ items: [item('a'), item('b')], hasMore: false } as never)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );

    const { result } = renderHook(() => useActionItems());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items.map((task) => task.id)).toEqual(['a', 'b']);

    act(() => {
      invalidateCache(invalidationPatterns.actionItems);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.items.map((task) => task.id)).toEqual(['a', 'b']);

    await act(async () => {
      resolveRefresh({ items: [item('a')], hasMore: false });
    });

    await waitFor(() =>
      expect(result.current.items.map((task) => task.id)).toEqual(['a']),
    );
    expect(result.current.loading).toBe(false);
  });

  it('coalesces the reloads a bulk delete triggers instead of one per deleted task', async () => {
    // The backend serves 12 list reads per minute per account
    // (`action_items:list` in backend/utils/rate_limit_config.py) and 429s the rest.
    const listReadsPerMinute = 12;
    const ids = Array.from({ length: 15 }, (_, index) => `task-${index}`);
    const serverIds = new Set(ids);
    let listReads = 0;
    vi.mocked(getActionItems).mockImplementation(async () => {
      listReads += 1;
      if (listReads > listReadsPerMinute) {
        throw new Error('API error: 429 Too Many Requests');
      }
      return { items: Array.from(serverIds, item), hasMore: false } as never;
    });
    // Like lib/api.ts: a DELETE that succeeds invalidates the action-items cache.
    vi.mocked(deleteActionItem).mockImplementation(async (id: string) => {
      await Promise.resolve();
      serverIds.delete(id);
      invalidateCache(invalidationPatterns.actionItems);
    });

    const { result } = renderHook(() => useActionItems());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toHaveLength(15);

    await act(async () => {
      await result.current.bulkDelete(ids);
    });

    // The initial load, the reload the first delete started, and one reload
    // queued behind it for the other fourteen deletes.
    await waitFor(() => expect(getActionItems).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(result.current.items).toEqual([]));
    expect(result.current.error).toBeNull();
  });

  it('only restores the tasks whose delete failed in a partly failed bulk delete', async () => {
    // The initial load resolves; the reload a successful delete's cache
    // invalidation triggers never resolves, so this isolates what bulkDelete
    // itself puts back from whatever a subsequent reload would later correct.
    let initialLoadServed = false;
    vi.mocked(getActionItems).mockImplementation(() => {
      if (!initialLoadServed) {
        initialLoadServed = true;
        return Promise.resolve({
          items: [item('a'), item('b'), item('c')],
          hasMore: false,
        } as never);
      }
      return new Promise(() => undefined);
    });
    // Like lib/api.ts: a DELETE that succeeds invalidates the action-items cache.
    vi.mocked(deleteActionItem).mockImplementation(async (id: string) => {
      if (id === 'b') {
        throw new Error('API error: 500 Internal Server Error');
      }
      invalidateCache(invalidationPatterns.actionItems);
    });

    const { result } = renderHook(() => useActionItems());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.bulkDelete(['a', 'b', 'c']);
    });

    // 'a' and 'c' were actually deleted server-side and must stay gone;
    // only 'b' (the failed delete) comes back.
    expect(result.current.items.map((task) => task.id)).toEqual(['b']);
    expect(result.current.error).not.toBeNull();
  });

  it('does not bring back a task deleted while an earlier reload was in flight', async () => {
    let answerFirstReload: () => void = () => undefined;
    let answerQueuedReload: () => void = () => undefined;
    vi.mocked(getActionItems)
      .mockResolvedValueOnce({
        items: [item('a'), item('b'), item('c')],
        hasMore: false,
      } as never)
      // The reload the first delete starts reads after `a` is gone but before
      // `b` is, and answers only after `b` has been deleted.
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            answerFirstReload = () =>
              resolve({ items: [item('b'), item('c')], hasMore: false } as never);
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            answerQueuedReload = () =>
              resolve({ items: [item('c')], hasMore: false } as never);
          }),
      );
    vi.mocked(deleteActionItem).mockImplementation(async () => {
      invalidateCache(invalidationPatterns.actionItems);
    });

    const { result } = renderHook(() => useActionItems());
    const shownIds = () => result.current.items.map((task) => task.id);
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.removeItem('a');
    });
    await act(async () => {
      await result.current.removeItem('b');
    });
    expect(shownIds()).toEqual(['c']);

    await act(async () => {
      answerFirstReload();
    });
    expect(shownIds()).toEqual(['c']);

    await act(async () => {
      answerQueuedReload();
    });
    expect(shownIds()).toEqual(['c']);
    expect(getActionItems).toHaveBeenCalledTimes(3);
  });
});
