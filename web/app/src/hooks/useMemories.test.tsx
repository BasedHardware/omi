import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMemories } from './useMemories';

const mocks = vi.hoisted(() => ({
  getMemoriesPage: vi.fn(),
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
  getCachedMemories: vi.fn(async (_scope?: unknown) => null),
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
    mocks.invalidationListeners.add(listener);
    return () => mocks.invalidationListeners.delete(listener);
  },
  invalidationPatterns: { memories: 'memories' },
  CACHE_TTL: { MEDIUM: 300000 },
  getMemoryBackendScope: () => mocks.backendScope,
  memoryCacheScopeKey: (scope: { ownerId: string; backendScope: string }) =>
    `${scope.ownerId}|${scope.backendScope}`,
  cacheKeys: {
    memories: (categories: string[], scope?: { ownerId: string; backendScope: string }) =>
      `memories:${scope ? `${scope.ownerId}|${scope.backendScope}` : 'unscoped'}:${
        categories.join(',') || 'all'
      }`,
  },
}));

vi.mock('@/lib/indexeddb', () => ({
  getCachedMemories: mocks.getCachedMemories,
  cacheMemories: mocks.cacheMemories,
  invalidateCache: mocks.invalidateMemoryCache,
}));

function page(content = 'A useful memory') {
  return {
    memories: [
      {
        id: `memory-${content}`,
        uid: mocks.authUser?.uid ?? 'signed-out',
        content,
        created_at: '2026-09-12T00:00:00.000Z',
        updated_at: '2026-09-12T00:00:00.000Z',
      },
    ],
    nextCursor: null,
    truncated: false,
  };
}

describe('useMemories standard list and cache scope', () => {
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
  });

  it('fetches the standard memory list without a belief view', async () => {
    mocks.getMemoriesPage.mockResolvedValueOnce(page());
    const { result } = renderHook(() => useMemories({ limit: 25 }));

    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(1));

    expect(mocks.getMemoriesPage.mock.calls[0][0]).toMatchObject({
      limit: 25,
      offset: 0,
    });
    expect(mocks.getMemoriesPage.mock.calls[0][0]).not.toHaveProperty('view');
    expect(result.current.memories[0]?.content).toBe('A useful memory');
    expect(result.current).not.toHaveProperty('beliefEnabled');
  });

  it('does not show owner A after sign-out and loads owner B without a reload', async () => {
    mocks.getMemoriesPage.mockImplementation(async () =>
      page(mocks.authUser?.uid === 'owner-a' ? 'Owner A memory' : 'Owner B memory'),
    );
    const { result, rerender } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Owner A memory'),
    );

    act(() => {
      mocks.authUser = null;
      rerender();
    });
    expect(result.current.memories).toEqual([]);

    act(() => {
      mocks.authUser = { uid: 'owner-b' };
      rerender();
    });
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Owner B memory'),
    );

    const scopesRead = mocks.getCachedMemories.mock.calls.map((call) => call[0]);
    expect(scopesRead).toEqual(
      expect.arrayContaining([
        { ownerId: 'owner-a', backendScope: 'https://backend-a' },
        { ownerId: 'owner-b', backendScope: 'https://backend-a' },
      ]),
    );
    expect(
      mocks.getCache.mock.calls.every(([key]) => !String(key).includes('unscoped')),
    ).toBe(true);
  });

  it('separates a backend change from the existing owner cache', async () => {
    mocks.getMemoriesPage.mockImplementation(async () =>
      page(
        mocks.backendScope.endsWith('backend-a')
          ? 'Backend A memory'
          : 'Backend B memory',
      ),
    );
    const { result, rerender } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Backend A memory'),
    );

    act(() => {
      mocks.backendScope = 'https://backend-b';
      rerender();
    });
    await waitFor(() =>
      expect(result.current.memories[0]?.content).toBe('Backend B memory'),
    );

    const cacheKeys = mocks.getCache.mock.calls.map(([key]) => String(key));
    expect(cacheKeys.some((key) => key.includes('https://backend-a'))).toBe(true);
    expect(cacheKeys.some((key) => key.includes('https://backend-b'))).toBe(true);
  });

  it('keeps pagination enabled when changing category filters', async () => {
    mocks.getMemoriesPage.mockResolvedValue({
      ...page(),
      nextCursor: 'next-page',
    });
    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.setCategories(['manual']));
    await waitFor(() => expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2));
    expect(mocks.getMemoriesPage.mock.calls[1][0]).toMatchObject({
      categories: ['manual'],
      offset: 0,
    });
    expect(result.current.hasMore).toBe(true);
  });

  it('clears an earlier fetch error when a cached category is shown', async () => {
    mocks.getMemoriesPage.mockResolvedValueOnce(page('All memories'));
    const { result } = renderHook(() => useMemories({ limit: 25 }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.memories[0]?.content).toBe('All memories');

    // The next category's first page fails, which shows the error banner.
    mocks.getMemoriesPage.mockRejectedValueOnce(new Error('Network error'));
    act(() => result.current.setCategories(['manual']));
    await waitFor(() => expect(result.current.error).toBe('Network error'));

    // The full list is still cached and fresh, so it comes back without a request.
    act(() => result.current.setCategories([]));
    expect(result.current.memories[0]?.content).toBe('All memories');
    expect(mocks.getMemoriesPage).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });
});
