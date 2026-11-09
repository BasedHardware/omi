import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearAllCache,
  invalidateCache,
  invalidationPatterns,
  setCache,
  cacheKeys,
  CACHE_TTL,
} from '@/lib/cache';

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

afterEach(() => {
  vi.useRealTimers();
});

describe('useConversations', () => {
  it('pages past an entirely failed cached page', async () => {
    setCache(
      cacheKeys.conversations(),
      {
        conversations: page(0, 50).map((c) => ({
          ...c,
          status: 'processing',
          home_step: 'failed',
        })),
        offset: 0,
        hasMore: true,
      },
      CACHE_TTL.MEDIUM,
    );
    const { result } = renderHook(() => useConversations({ limit: 50 }));
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));
    expect(getConversations).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getConversations).mock.calls[0][0]?.offset).toBe(50);
    expect(ids(result.current.conversations)).toContain('c50');
  });

  it('does not page a new cached filter using a hidden previous list', async () => {
    setCache(
      cacheKeys.conversations(),
      {
        conversations: page(0, 50).map((c) => ({
          ...c,
          status: 'processing',
          home_step: 'failed',
        })),
        offset: 50,
        hasMore: true,
      },
      CACHE_TTL.MEDIUM,
    );
    setCache(
      cacheKeys.conversations('work'),
      {
        conversations: WORK,
        offset: 0,
        hasMore: false,
      },
      CACHE_TTL.MEDIUM,
    );
    const { result, rerender } = renderHook(
      ({ enabled, folderId }: { enabled: boolean; folderId?: string }) =>
        useConversations({ enabled, folderId }),
      { initialProps: { enabled: false, folderId: undefined as string | undefined } },
    );
    rerender({ enabled: true, folderId: 'work' });
    expect(ids(result.current.conversations)).toEqual(['w1']);
    await act(async () => {});
    expect(getConversations).not.toHaveBeenCalled();
  });

  it('hides failed projections from the feed and date groups, including cached pages', async () => {
    vi.mocked(getConversations).mockResolvedValueOnce([
      { ...page(0, 1)[0], status: 'processing', home_step: 'failed' },
      ...page(1, 1),
    ] as never);
    const first = renderHook(() => useConversations());
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(ids(first.result.current.conversations)).toEqual(['c1']);
    expect(
      Object.values(first.result.current.groupedConversations)
        .flat()
        .map((c) => c.id),
    ).toEqual(['c1']);
    first.unmount();
    const cached = renderHook(() => useConversations());
    expect(ids(cached.result.current.conversations)).toEqual(['c1']);
    expect(getConversations).toHaveBeenCalledTimes(1);
  });

  it('keeps raw page offsets when an entire page is hidden', async () => {
    vi.mocked(getConversations).mockResolvedValueOnce(
      page(0, 50).map((c) => ({
        ...c,
        status: 'processing',
        home_step: 'failed',
      })) as never,
    );
    const { result } = renderHook(() => useConversations({ limit: 50 }));
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));
    expect(vi.mocked(getConversations).mock.calls.at(-1)![0]?.offset).toBe(50);
    expect(ids(result.current.conversations)).toContain('c50');
    expect(result.current.hasMore).toBe(true);
    await act(async () => {
      await result.current.loadMore();
    });
    expect(vi.mocked(getConversations).mock.calls.at(-1)![0]?.offset).toBe(100);
    expect(ids(result.current.conversations)).toContain('c100');
  });

  it('stops paging a fully hidden feed at the server page boundary', async () => {
    vi.mocked(getConversations)
      .mockResolvedValueOnce(
        page(0, 50).map((c) => ({
          ...c,
          status: 'processing',
          home_step: 'failed',
        })) as never,
      )
      .mockResolvedValueOnce([]);
    const { result } = renderHook(() => useConversations({ limit: 50 }));
    await waitFor(() => expect(result.current.hasMore).toBe(false));
    expect(result.current.conversations).toEqual([]);
    expect(getConversations).toHaveBeenCalledTimes(2);
  });

  it.each([undefined, null, 'processing'])(
    'keeps legacy processing visible and polling for home_step=%s',
    async (home_step) => {
      vi.useFakeTimers();
      vi.mocked(getConversations).mockResolvedValue([
        { ...page(0, 1)[0], status: 'processing', home_step },
      ] as never);
      const { result } = renderHook(() => useConversations());
      await act(async () => {});
      expect(ids(result.current.conversations)).toEqual(['c0']);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      expect(getConversations).toHaveBeenCalledTimes(2);
    },
  );

  it('stops polling when the server projects a processing row as failed', async () => {
    vi.useFakeTimers();
    const active = { ...page(0, 1)[0], status: 'processing' };
    vi.mocked(getConversations)
      .mockResolvedValueOnce([active] as never)
      .mockResolvedValue([{ ...active, home_step: 'failed' }] as never);
    const { result } = renderHook(() => useConversations());
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.conversations).toEqual([]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(getConversations).toHaveBeenCalledTimes(2);
  });

  it('does not start polling for failed processing rows', async () => {
    vi.useFakeTimers();
    vi.mocked(getConversations).mockResolvedValue([
      { ...page(0, 1)[0], status: 'processing', home_step: 'failed' },
    ] as never);
    const { result } = renderHook(() => useConversations());
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(result.current.conversations).toEqual([]);
    expect(getConversations).toHaveBeenCalledTimes(1);
  });

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
