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

const WORK = [{ id: 'w1', created_at: '2026-09-02T00:00:00.000Z', status: 'completed' }];

type Filters = { folderId?: string };

function renderConversations(initialProps: Filters) {
  return renderHook(
    ({ folderId }: Filters) => useConversations({ limit: 50, folderId }),
    { initialProps },
  );
}

function ids(conversations: { id: string }[]) {
  return conversations.map((c) => c.id);
}

// The work folder answers at once; a request for All waits until the test answers it.
function holdAllRequests() {
  let answer: (conversations: unknown) => void = () => {};
  vi.mocked(getConversations).mockImplementation((params) =>
    params?.folderId === 'work'
      ? (Promise.resolve(WORK) as never)
      : (new Promise((resolve) => {
          answer = resolve;
        }) as never),
  );
  return (conversations: unknown) => answer(conversations);
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

  it('loads a folder picked while the previous list is still loading', async () => {
    const answerAll = holdAllRequests();
    const { result, rerender } = renderConversations({});

    rerender({ folderId: 'work' });
    await waitFor(() => expect(ids(result.current.conversations)).toEqual(['w1']));
    expect(vi.mocked(getConversations).mock.calls.at(-1)![0]).toMatchObject({
      folderId: 'work',
    });

    // All's first page answers last and must not replace the folder's list.
    await act(async () => {
      answerAll(page(0, 50));
    });
    expect(ids(result.current.conversations)).toEqual(['w1']);
    expect(result.current.loading).toBe(false);
  });

  it('keeps a cached folder when the list it left for answers late', async () => {
    const answerAll = holdAllRequests();
    const { result, rerender } = renderConversations({ folderId: 'work' });
    await waitFor(() => expect(ids(result.current.conversations)).toEqual(['w1']));

    // Open All, whose first page is still loading, then go back to the cached folder.
    rerender({});
    rerender({ folderId: 'work' });
    expect(ids(result.current.conversations)).toEqual(['w1']);

    await act(async () => {
      answerAll(page(0, 50));
    });
    expect(ids(result.current.conversations)).toEqual(['w1']);
  });

  it('ignores a refresh started for a folder that is no longer shown', async () => {
    vi.mocked(getConversations).mockImplementation(
      async (params) => (params?.folderId === 'work' ? WORK : page(0, 50)) as never,
    );
    const { result, rerender } = renderConversations({ folderId: 'work' });
    await waitFor(() => expect(ids(result.current.conversations)).toEqual(['w1']));
    // Captured while the folder was shown, as by a handler that refreshes after an
    // await: deleting the folder being viewed switches to All before it refreshes.
    const refreshWork = result.current.refresh;

    rerender({});
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));

    await act(async () => {
      await refreshWork();
    });

    expect(result.current.conversations).toHaveLength(50);
    expect(result.current.loading).toBe(false);
    expect(getConversations).toHaveBeenCalledTimes(2);
  });

  it("clears the previous filter's conversations when switching to an uncached filter", async () => {
    const { result, rerender } = renderHook(
      ({ folderId }: { folderId: string }) => useConversations({ limit: 50, folderId }),
      { initialProps: { folderId: 'home' } },
    );
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));

    let rejectWork!: (error: Error) => void;
    vi.mocked(getConversations).mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectWork = reject;
        }) as never,
    );

    rerender({ folderId: 'work' });
    expect(result.current.conversations).toEqual([]);
    expect(result.current.loading).toBe(true);

    await act(async () => {
      rejectWork(new Error('Network error'));
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.conversations).toEqual([]);
  });
});
