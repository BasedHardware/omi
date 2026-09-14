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
  onCacheInvalidation: vi.fn(() => () => {}),
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

function page(beliefEnabled: boolean | null, content = 'A useful memory') {
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
    let resolveRefresh: (value: ReturnType<typeof page>) => void = () => {};
    const pendingRefresh = new Promise<ReturnType<typeof page>>((resolve) => {
      resolveRefresh = resolve;
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

    let firstResult = true;
    await act(async () => {
      firstResult = await result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(firstResult).toBe(false);
    const firstFeedbackId = mocks.setMemoryUseRequest.mock.calls[0][2];

    resolveRefresh(page(true));
    await act(async () => {
      await refreshPromise;
    });

    let secondResult = false;
    await act(async () => {
      secondResult = await result.current.setMemoryUse('memory-owner-a', 'useful');
    });
    expect(secondResult).toBe(true);
    expect(mocks.setMemoryUseRequest.mock.calls[1][2]).toBe(firstFeedbackId);
  });
});
