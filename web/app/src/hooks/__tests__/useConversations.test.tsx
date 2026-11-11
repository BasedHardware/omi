import { act, renderHook, waitFor } from '@testing-library/react';
import {
  conversationsForSurface,
  isConversationProcessing,
} from '@/lib/conversationHome';
import { useActivityFailures } from '@/hooks/useActivityFailures';
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
  it('restarts processing without home_step and immediately removes the Activity failure', async () => {
    const failed = { ...page(0, 1)[0], status: 'processing', home_step: 'failed' };
    vi.mocked(getConversations).mockResolvedValueOnce([failed] as never);
    const empty: import('@/types/conversation').Conversation[] = [];
    const { result, unmount } = renderHook(() => {
      const list = useConversations({ limit: 50 });
      const activity = useActivityFailures(list.conversations, empty, 'owner');
      return { ...list, failures: activity.failures };
    });
    await waitFor(() => expect(result.current.failures).toHaveLength(1));
    // The retry endpoint omits the list-only home_step field.
    const processing = {
      ...page(0, 1)[0],
      status: 'processing',
    } as import('@/types/conversation').Conversation;
    act(() => result.current.replaceConversation(processing));
    expect(result.current.conversations[0].home_step).toBeUndefined();
    expect(isConversationProcessing(result.current.conversations[0])).toBe(true);
    expect(result.current.failures).toEqual([]);
    expect(conversationsForSurface(result.current.conversations, false, true)).toEqual([
      processing,
    ]);
    vi.mocked(getConversations).mockRejectedValueOnce(new Error('offline'));
    await act(async () => result.current.refresh());
    expect(result.current.failures).toEqual([]);
    unmount();
    const remounted = renderConversations({});
    expect(remounted.result.current.conversations[0]).toEqual(processing);
  });

  it('does not let a pre-retry refresh resurrect a completed Activity row', async () => {
    const failed = { ...page(0, 1)[0], status: 'processing', home_step: 'failed' };
    vi.mocked(getConversations).mockResolvedValueOnce([failed] as never);
    const { result } = renderConversations({});
    await waitFor(() =>
      expect(result.current.conversations[0]?.home_step).toBe('failed'),
    );
    let finish!: (rows: never) => void;
    vi.mocked(getConversations).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.refresh();
    });
    const completed = {
      ...result.current.conversations[0],
      status: 'completed',
      home_step: 'done',
    } as import('@/types/conversation').Conversation;
    act(() => result.current.replaceConversation(completed));
    await act(async () => {
      finish([failed] as never);
      await pending;
    });
    expect(result.current.conversations[0]).toEqual(completed);
  });

  it('applies retry completion immediately and keeps it through a failed refresh and cache remount', async () => {
    const failed = { ...page(0, 1)[0], status: 'processing', home_step: 'failed' };
    vi.mocked(getConversations).mockResolvedValueOnce([failed] as never);
    const { result, unmount } = renderConversations({});
    await waitFor(() =>
      expect(result.current.conversations[0]?.home_step).toBe('failed'),
    );
    const completed = {
      ...result.current.conversations[0],
      status: 'completed',
      home_step: 'done',
    } as import('@/types/conversation').Conversation;
    act(() => result.current.replaceConversation(completed));
    expect(result.current.conversations[0]).toEqual(completed);
    vi.mocked(getConversations).mockRejectedValueOnce(new Error('offline'));
    await act(async () => result.current.refresh());
    expect(result.current.conversations[0]).toEqual(completed);
    unmount();
    const remounted = renderConversations({});
    expect(remounted.result.current.conversations[0]).toEqual(completed);
  });

  it('keeps a failed cached page openable without unsolicited pagination', async () => {
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
    expect(result.current.conversations).toHaveLength(50);
    expect(ids(result.current.conversations)).toContain('c0');
    await act(async () => {});
    expect(getConversations).not.toHaveBeenCalled();
  });

  it('does not page a new cached filter using a failed previous list', async () => {
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

  it('keeps failed projections in the feed and date groups, including cached pages', async () => {
    vi.mocked(getConversations).mockResolvedValueOnce([
      { ...page(0, 1)[0], status: 'processing', home_step: 'failed' },
      ...page(1, 1),
    ] as never);
    const first = renderHook(() => useConversations());
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(ids(first.result.current.conversations)).toEqual(['c0', 'c1']);
    expect(
      Object.values(first.result.current.groupedConversations)
        .flat()
        .map((c) => c.id),
    ).toEqual(['c0', 'c1']);
    first.unmount();
    const cached = renderHook(() => useConversations());
    expect(ids(cached.result.current.conversations)).toEqual(['c0', 'c1']);
    expect(getConversations).toHaveBeenCalledTimes(1);
  });

  it('pages normally after a failed page without changing offsets', async () => {
    vi.mocked(getConversations).mockResolvedValueOnce(
      page(0, 50).map((c) => ({
        ...c,
        status: 'processing',
        home_step: 'failed',
      })) as never,
    );
    const { result } = renderHook(() => useConversations({ limit: 50 }));
    await waitFor(() => expect(result.current.conversations).toHaveLength(50));
    expect(getConversations).toHaveBeenCalledTimes(1);
    await act(async () => {
      await result.current.loadMore();
    });
    expect(vi.mocked(getConversations).mock.calls.at(-1)![0]?.offset).toBe(50);
    expect(result.current.conversations).toHaveLength(100);
    expect(ids(result.current.conversations)).toContain('c0');
    expect(ids(result.current.conversations)).toContain('c50');
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
    expect(ids(result.current.conversations)).toEqual(['c0']);
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
    expect(ids(result.current.conversations)).toEqual(['c0']);
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
