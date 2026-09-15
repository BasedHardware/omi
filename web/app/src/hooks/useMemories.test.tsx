import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMemories } from './useMemories';

const mocks = vi.hoisted(() => ({
  getMemoriesPage: vi.fn(),
  setMemoryUseRequest: vi.fn(),
  getCache: vi.fn(),
  setCache: vi.fn(),
  updateCache: vi.fn(),
  deleteCachePattern: vi.fn(),
  invalidateMemoryCache: vi.fn(),
  cacheEntries: new Map<string, { data: unknown; isStale: boolean }>(),
  invalidationListeners: new Set<(pattern: string) => void>(),
  authUser: { uid: 'owner-a' } as { uid: string } | null,
  authLoading: false,
  backendScope: 'https://backend-a',
  getCachedMemories: vi.fn(async (_memoryView?: string, _scope?: unknown) => null),
  cacheMemories: vi.fn(async () => {}),
}));

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({ user: mocks.authUser, loading: mocks.authLoading }),
}));

vi.mock('@/lib/api', () => ({
  getMemoriesPage: mocks.getMemoriesPage,
  createMemory: vi.fn(),
  updateMemoryContent: vi.fn(),
  updateMemoryVisibility: vi.fn(),
  setMemoryUse: mocks.setMemoryUseRequest,
  deleteMemory: vi.fn(),
  deleteMemoriesBatch: vi.fn(),
  reviewMemory: vi.fn(),
}));

vi.mock('@/lib/cache', () => ({
  getCache: mocks.getCache,
  setCache: mocks.setCache,
  updateCache: mocks.updateCache,
  deleteCachePattern: mocks.deleteCachePattern,
  onCacheInvalidation: (listener: (pattern: string) => void) => {
    // Mirror cache.ts: registered listeners fire synchronously from
    // invalidateCache, before its caller resumes.
    mocks.invalidationListeners.add(listener);
    return () => mocks.invalidationListeners.delete(listener);
  },
  invalidationPatterns: { memories: 'memories' },
  CACHE_TTL: { MEDIUM: 300000 },
  getMemoryBackendScope: () => mocks.backendScope,
  memoryCacheScopeKey: (scope: { ownerId: string; backendScope: string }) =>
    `${scope.ownerId}|${scope.backendScope}`,
  cacheKeys: {
    memories: (
      _categories: string[],
      view: string,
      scope?: { ownerId: string; backendScope: string },
    ) =>
      `memories:${scope ? `${scope.ownerId}|${scope.backendScope}` : 'unscoped'}:${view}`,
  },
}));

vi.mock('@/lib/indexeddb', () => ({
  getCachedMemories: mocks.getCachedMemories,
  cacheMemories: mocks.cacheMemories,
  invalidateCache: mocks.invalidateMemoryCache,
}));

/** Page shape returned by the mocked getMemoriesPage. */
interface MemoryPage {
  memories: Array<{
    id: string;
    uid: string;
    content: string;
    created_at: string;
    updated_at: string;
  }>;
  nextCursor: string | null;
  truncated: boolean;
  beliefEnabled: boolean | null;
}

function page(beliefEnabled: boolean | null, content = 'A useful memory'): MemoryPage {
  return {
    memories: [
      {
        id: `memory-${mocks.authUser?.uid ?? 'signed-out'}`,
        uid: mocks.authUser?.uid ?? 'signed-out',
        content,
        created_at: '2026-09-12T00:00:00.000Z',
        updated_at: '2026-09-12T00:00:00.000Z',
      },
    ],
    nextCursor: null,
    truncated: false,
    beliefEnabled,
  };
}

describe('useMemories beta capability negotiation and cache scope', () => {
  beforeEach(() => {
    mocks.authUser = { uid: 'owner-a' };
    mocks.authLoading = false;
    mocks.backendScope = 'https://backend-a';
    mocks.cacheEntries.clear();
    mocks.invalidationListeners.clear();
    mocks.getCache.mockImplementation(
      (key: string) => mocks.cacheEntries.get(key) ?? null,
    );
    mocks.setCache.mockImplementation((key: string, data: unknown) => {
      mocks.cacheEntries.set(key, { data, isStale: false });
    });
    mocks.updateCache.mockReset();
    mocks.deleteCachePattern.mockReset();
    mocks.invalidateMemoryCache.mockReset();
    mocks.getCachedMemories.mockReset();
    mocks.getCachedMemories.mockResolvedValue(null);
    mocks.cacheMemories.mockReset();
    mocks.cacheMemories.mockResolvedValue(undefined);
    mocks.getMemoriesPage.mockReset();
    mocks.setMemoryUseRequest.mockReset();
    mocks.setMemoryUseRequest.mockResolvedValue(undefined);
  });

  it('discovers capability without a view query, then refreshes the default Useful now view', async () => {
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true));

    const { result } = renderHook(() => useMemories({ limit: 25 }));

    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    expect(mocks.getMemoriesPage.mock.calls[0][0].view).toBeUndefined();
    expect(mocks.getMemoriesPage.mock.calls[1][0]).toMatchObject({
      limit: 25,
      offset: 0,
      view: 'useful_now',
    });
    expect(result.current.beliefEnabled).toBe(true);
  });

  it('drops cached beta state and reissues an unqualified request when capability is withdrawn', async () => {
    mocks.cacheEntries.set('memories:owner-a|https://backend-a:useful_now', {
      data: {
        memories: [page(true).memories[0]],
        offset: 1,
        nextCursor: null,
        hasMore: false,
        truncated: false,
        beliefEnabled: true,
      },
      isStale: false,
    });
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(false))
      .mockResolvedValueOnce(page(false));

    const { result } = renderHook(() => useMemories({ limit: 25 }));

    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    expect(mocks.getMemoriesPage.mock.calls[0][0]).toMatchObject({
      view: 'useful_now',
    });
    expect(mocks.getMemoriesPage.mock.calls[1][0].view).toBeUndefined();
    expect(result.current.memoryView).toBe('useful_now');
    expect(result.current.beliefEnabled).toBe(false);
    expect(mocks.deleteCachePattern).toHaveBeenCalledWith('memories', {
      ownerId: 'owner-a',
      backendScope: 'https://backend-a',
    });
    expect(mocks.invalidateMemoryCache).toHaveBeenCalledOnce();
  });

  it('does not show owner A after sign-out and loads owner B without a reload', async () => {
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true, 'Owner A memory'))
      .mockResolvedValueOnce(page(true, 'Owner A memory'))
      .mockResolvedValueOnce(page(true, 'Owner B memory'))
      .mockResolvedValueOnce(page(true, 'Owner B memory'));

    const { result, rerender } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Owner A memory'),
    );

    act(() => {
      mocks.authUser = null;
      rerender();
    });
    expect(result.current.memories).toEqual([]);
    expect(result.current.beliefEnabled).toBeNull();

    act(() => {
      mocks.authUser = { uid: 'owner-b' };
      rerender();
    });
    expect(result.current.memories).toEqual([]);
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Owner B memory'),
    );

    const scopesRead = mocks.getCachedMemories.mock.calls.map((call) => call[1]);
    expect(scopesRead).toEqual(
      expect.arrayContaining([
        { ownerId: 'owner-a', backendScope: 'https://backend-a' },
        { ownerId: 'owner-b', backendScope: 'https://backend-a' },
      ]),
    );
    expect(
      mocks.getCache.mock.calls.every(
        ([key]) => !String(key).startsWith('memories:unscoped'),
      ),
    ).toBe(true);
  });

  it('separates a backend change even when the old backend has cached beta capability', async () => {
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true, 'Backend A memory'))
      .mockResolvedValueOnce(page(true, 'Backend A memory'))
      .mockResolvedValueOnce(page(true, 'Backend B memory'))
      .mockResolvedValueOnce(page(true, 'Backend B memory'));

    const { result, rerender } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Backend A memory'),
    );

    mocks.backendScope = 'https://backend-b';
    act(() => rerender());
    expect(result.current.memories).toEqual([]);
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Backend B memory'),
    );

    const cacheKeys = mocks.getCache.mock.calls.map(([key]) => String(key));
    expect(cacheKeys.some((key) => key.includes('https://backend-a'))).toBe(true);
    expect(cacheKeys.some((key) => key.includes('https://backend-b'))).toBe(true);
    expect(mocks.getMemoriesPage.mock.calls[2][0].view).toBeUndefined();
  });

  it('reuses feedback id when canonical refresh is still in flight', async () => {
    let rejectRefresh: (reason?: unknown) => void = () => {};
    const pendingRefresh = new Promise<MemoryPage>((_resolve, reject) => {
      rejectRefresh = reject;
    });
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true))
      .mockReturnValueOnce(pendingRefresh)
      .mockResolvedValueOnce(page(true));

    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    const refreshPromise = result.current.refresh();
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(3));

    // The use-feedback request joins the in-flight canonical refresh instead
    // of reporting failure, then fails with it when the canonical read errors.
    let setMemoryUsePromise: Promise<boolean> | undefined;
    await act(async () => {
      setMemoryUsePromise = result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(mocks.setMemoryUseRequest).toHaveBeenCalledTimes(1);
    const firstFeedbackId = mocks.setMemoryUseRequest.mock.calls[0][2];

    let outcome = true;
    await act(async () => {
      rejectRefresh(new Error('canonical read failed'));
      outcome = await setMemoryUsePromise!;
      await refreshPromise;
    });
    expect(outcome).toBe(false);

    // The failed canonical read keeps the feedback id so the retry reuses it.
    let retryOutcome = false;
    await act(async () => {
      retryOutcome = await result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(retryOutcome).toBe(true);
    expect(mocks.setMemoryUseRequest.mock.calls[1][2]).toBe(firstFeedbackId);
  });

  it('awaits the invalidation-triggered refresh and reports success after commit', async () => {
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true, 'Useful after feedback'));
    // api.ts fires invalidation listeners synchronously once the POST
    // commits, before the awaiting use-feedback caller resumes.
    mocks.setMemoryUseRequest.mockImplementation(async () => {
      mocks.invalidationListeners.forEach((listener) => listener('memories'));
    });

    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    let outcome = false;
    await act(async () => {
      outcome = await result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(outcome).toBe(true);
    // The invalidation-triggered refresh is the canonical read: exactly one
    // post-commit fetch, joined by the use-feedback re-read.
    expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(3);
    const firstFeedbackId = mocks.setMemoryUseRequest.mock.calls[0][2];

    // Success releases the feedback id: a repeat action gets a fresh one.
    mocks.setMemoryUseRequest.mockReset();
    mocks.setMemoryUseRequest.mockResolvedValue(undefined);
    mocks.getMemoriesPage.mockResolvedValueOnce(page(true));
    let repeatOutcome = false;
    await act(async () => {
      repeatOutcome = await result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(repeatOutcome).toBe(true);
    expect(mocks.setMemoryUseRequest.mock.calls[0][2]).not.toBe(firstFeedbackId);
  });

  it('fetches the newly selected view after a refresh that was in flight when the view changed', async () => {
    let resolveRefresh: (value: MemoryPage) => void = () => {};
    const pendingRefresh = new Promise<MemoryPage>((resolve) => {
      resolveRefresh = resolve;
    });
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true))
      .mockReturnValueOnce(pendingRefresh)
      .mockResolvedValueOnce(page(true, 'History memory'));

    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    const refreshPromise = result.current.refresh();
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(3));

    act(() => {
      result.current.setMemoryView('history');
    });

    resolveRefresh(page(true));
    await act(async () => {
      await refreshPromise;
    });

    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('History memory'),
    );
    expect(mocks.getMemoriesPage.mock.calls[3][0]).toMatchObject({ view: 'history' });
  });

  it('does not apply the previous view page after the view changes', async () => {
    let resolveHistory: (value: MemoryPage) => void = () => {};
    const pendingHistory = new Promise<MemoryPage>((resolve) => {
      resolveHistory = resolve;
    });
    mocks.getMemoriesPage
      .mockResolvedValueOnce(page(true))
      .mockResolvedValueOnce(page(true))
      .mockReturnValueOnce(pendingHistory)
      .mockResolvedValueOnce(page(true, 'All memory'));

    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));

    act(() => {
      result.current.setMemoryView('history');
    });
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(3));

    act(() => {
      result.current.setMemoryView('all');
    });

    resolveHistory(page(true, 'History memory'));
    await act(async () => {
      await pendingHistory;
    });

    // The stale history page never lands; the 'all' fetch replaces the list.
    await waitFor(() => expect(result.current.memories[0]?.content).toBe('All memory'));
    expect(
      result.current.memories.some((memory) => memory.content === 'History memory'),
    ).toBe(false);
    expect(mocks.getMemoriesPage.mock.calls[3][0]).toMatchObject({ view: 'all' });
  });
});
