'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import type { Memory, MemoryCategory, MemoryVisibility } from '@/types/conversation';
import {
  getMemories,
  createMemory,
  updateMemoryContent,
  updateMemoryVisibility,
  deleteMemory,
  deleteMemoriesBatch,
  reviewMemory,
} from '@/features/memories/api';
import {
  getCache,
  setCache,
  updateCache,
  onCacheInvalidation,
  invalidationPatterns,
  CACHE_TTL,
  cacheKeys,
} from '@/lib/cache';
import { getCachedMemories, cacheMemories } from '@/lib/indexeddb';

export interface UseMemoriesOptions {
  categories?: MemoryCategory[];
  limit?: number;
}

/** Outcome of a chunked bulk delete. */
export interface RemoveMemoriesResult {
  /** Whether every chunk succeeded. */
  success: boolean;
  /** IDs confirmed deleted across successful chunks (empty unless chunks ran). */
  deletedIds: string[];
}

export interface UseMemoriesReturn {
  memories: Memory[];
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  addMemory: (content: string, visibility?: MemoryVisibility) => Promise<Memory | null>;
  editMemory: (id: string, content: string) => Promise<boolean>;
  removeMemory: (id: string) => Promise<boolean>;
  removeMemories: (ids: string[]) => Promise<RemoveMemoriesResult>;
  toggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  acceptMemory: (id: string) => Promise<boolean>;
  rejectMemory: (id: string) => Promise<boolean>;
  setCategories: (categories: MemoryCategory[]) => void;
  activeCategories: MemoryCategory[];
}

interface CacheEntry {
  memories: Memory[];
  offset: number;
  hasMore: boolean;
}

function getCacheKey(categories: MemoryCategory[]): string {
  return cacheKeys.memories(categories.length === 0 ? [] : [...categories].sort());
}

function getFromCache(key: string): CacheEntry | null {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.data : null;
}

function setToCache(
  key: string,
  memories: Memory[],
  offset: number,
  hasMore: boolean,
): void {
  setCache<CacheEntry>(key, { memories, offset, hasMore }, CACHE_TTL.MEDIUM);
}

function updateCacheMemories(
  key: string,
  updater: (memories: Memory[]) => Memory[],
): void {
  updateCache<CacheEntry>(key, (entry) => ({
    ...entry,
    memories: updater(entry.memories),
  }));
}

function isCacheStale(key: string): boolean {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.isStale : true;
}

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export function createMemoriesStore(limit: number, initialCategories: MemoryCategory[]) {
  const initialKey = getCacheKey(initialCategories);
  const cachedEntry = getFromCache(initialKey);

  const memories = createSignal<Memory[]>(cachedEntry?.memories ?? []);
  const loading = createSignal(!cachedEntry);
  const error = createSignal<string | null>(null);
  const hasMore = createSignal(cachedEntry?.hasMore ?? true);
  const activeCategories = createSignal<MemoryCategory[]>(initialCategories);
  let offset = cachedEntry?.offset ?? 0;
  let fetching = false;
  let initialized = false;
  const mutationTails = new Map<string, Promise<void>>();

  const enqueueMutation = <T>(id: string, mutation: () => Promise<T>): Promise<T> => {
    const previous = mutationTails.get(id);
    const result = previous ? previous.then(mutation) : mutation();
    const tail = result.then(
      () => undefined,
      () => undefined,
    );
    mutationTails.set(id, tail);
    void tail.then(() => {
      if (mutationTails.get(id) === tail) mutationTails.delete(id);
    });
    return result;
  };

  const cacheKey = () => getCacheKey(activeCategories.peek());

  const persistList = (list: Memory[], nextOffset: number, nextHasMore: boolean) => {
    setToCache(cacheKey(), list, nextOffset, nextHasMore);
  };

  const applyAndCache = (updater: (prev: Memory[]) => Memory[]) => {
    const updated = updater(memories.peek());
    memories.set(updated);
    updateCacheMemories(cacheKey(), updater);
  };

  const doFetch = async (
    categories: MemoryCategory[],
    currentOffset: number,
  ): Promise<Memory[]> => {
    return getMemories({
      limit,
      offset: currentOffset,
      categories: categories.length > 0 ? categories : undefined,
    });
  };

  const loadInitial = async () => {
    if (initialized) return;
    initialized = true;

    const categories = activeCategories.peek();
    const key = getCacheKey(categories);
    const cached = getFromCache(key);

    if (cached && !isCacheStale(key)) {
      memories.set(cached.memories);
      hasMore.set(cached.hasMore);
      offset = cached.offset;
      loading.set(false);
      return;
    }

    if (cached) {
      memories.set(cached.memories);
      hasMore.set(cached.hasMore);
      offset = cached.offset;
      loading.set(false);
    }

    if (fetching) return;
    fetching = true;

    if (!cached) {
      const indexedDBMemories = await getCachedMemories();
      if (indexedDBMemories && indexedDBMemories.length > 0) {
        console.log('[useMemories] Loaded from IndexedDB');
        memories.set(indexedDBMemories);
        offset = indexedDBMemories.length;
        hasMore.set(indexedDBMemories.length >= limit);
        setToCache(
          key,
          indexedDBMemories,
          indexedDBMemories.length,
          indexedDBMemories.length >= limit,
        );
        loading.set(false);
      } else {
        loading.set(true);
      }
    } else {
      loading.set(false);
    }

    error.set(null);

    try {
      const result = await doFetch(categories, 0);
      memories.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(key, result, result.length, result.length >= limit);
      await cacheMemories(result);
    } catch (err) {
      let hasAnyCachedData = !!cached;
      if (!hasAnyCachedData) {
        try {
          const indexedDbMemories = await getCachedMemories();
          hasAnyCachedData = !!indexedDbMemories;
        } catch {
          // If reading from IndexedDB fails, don't mask the original error
        }
      }

      const baseMessage = messageFor(err, 'Failed to load memories');
      if (hasAnyCachedData) {
        error.set(`${baseMessage} (showing cached data)`);
      } else {
        error.set(baseMessage);
      }
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const loadForCategories = async () => {
    const categories = activeCategories.peek();
    const key = getCacheKey(categories);
    const cached = getFromCache(key);

    if (cached) {
      memories.set(cached.memories);
      hasMore.set(cached.hasMore);
      offset = cached.offset;
      if (!isCacheStale(key)) {
        return;
      }
    }

    if (fetching) return;
    fetching = true;
    if (!cached) {
      loading.set(true);
    }
    error.set(null);

    try {
      const result = await doFetch(categories, 0);
      memories.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(key, result, result.length, result.length >= limit);
    } catch (err) {
      if (!cached) {
        error.set(messageFor(err, 'Failed to load memories'));
      }
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const reloadAfterInvalidation = async () => {
    if (fetching) return;
    fetching = true;
    const categories = activeCategories.peek();
    const key = getCacheKey(categories);
    try {
      const result = await doFetch(categories, 0);
      memories.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(key, result, result.length, result.length >= limit);
    } catch (err) {
      console.error('Failed to refresh memories after invalidation:', err);
    } finally {
      fetching = false;
    }
  };

  const loadMore = async () => {
    if (fetching || !hasMore.peek()) return;
    fetching = true;
    loading.set(true);
    const categories = activeCategories.peek();
    const key = getCacheKey(categories);

    try {
      const result = await doFetch(categories, offset);
      const existingIds = new Set(memories.peek().map((m) => m.id));
      const newMemories = result.filter((m) => !existingIds.has(m.id));
      const updated = [...memories.peek(), ...newMemories];
      memories.set(updated);
      offset += result.length;
      const nextHasMore = result.length >= limit;
      hasMore.set(nextHasMore);
      setToCache(key, updated, offset, nextHasMore);
    } catch (err) {
      error.set(messageFor(err, 'Failed to load more memories'));
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const refresh = async () => {
    if (fetching) return;
    fetching = true;
    loading.set(true);
    error.set(null);
    const categories = activeCategories.peek();
    const key = getCacheKey(categories);

    try {
      const result = await doFetch(categories, 0);
      memories.set(result);
      offset = result.length;
      hasMore.set(result.length >= limit);
      setToCache(key, result, result.length, result.length >= limit);
    } catch (err) {
      error.set(messageFor(err, 'Failed to refresh memories'));
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const setCategories = (categories: MemoryCategory[]) => {
    const previous = JSON.stringify(activeCategories.peek());
    const next = JSON.stringify(categories);
    if (previous === next) return;
    activeCategories.set(categories);
    offset = 0;
    void loadForCategories();
  };

  const addMemory = async (
    content: string,
    visibility: MemoryVisibility = 'public',
  ): Promise<Memory | null> => {
    try {
      const newMemory = await createMemory({ content, visibility, category: 'manual' });
      applyAndCache((prev) => [newMemory, ...prev]);
      error.set(null);
      return newMemory;
    } catch (err) {
      error.set(messageFor(err, 'Failed to create memory'));
      return null;
    }
  };

  const editMemory = (id: string, content: string): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = memories.peek().find((m) => m.id === id);
      applyAndCache((prev) =>
        prev.map((m) =>
          m.id === id
            ? { ...m, content, edited: true, updated_at: new Date().toISOString() }
            : m,
        ),
      );

      try {
        await updateMemoryContent(id, content);
        error.set(null);
        return true;
      } catch (err) {
        if (previous) {
          applyAndCache((prev) => prev.map((m) => (m.id === id ? previous : m)));
        }
        error.set(messageFor(err, 'Failed to update memory'));
        return false;
      }
    });

  const removeMemory = (id: string): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = memories.peek();
      applyAndCache((prev) => prev.filter((m) => m.id !== id));

      try {
        await deleteMemory(id);
        error.set(null);
        return true;
      } catch (err) {
        memories.set(previous);
        updateCacheMemories(cacheKey(), () => previous);
        error.set(messageFor(err, 'Failed to delete memory'));
        return false;
      }
    });

  const removeMemories = async (ids: string[]): Promise<RemoveMemoriesResult> => {
    if (ids.length === 0) return { success: true, deletedIds: [] };
    const CHUNK_SIZE = 100;
    const deletedIds: string[] = [];
    try {
      for (let i = 0; i < ids.length; i += CHUNK_SIZE) {
        const chunk = ids.slice(i, i + CHUNK_SIZE);
        await deleteMemoriesBatch(chunk);
        deletedIds.push(...chunk);
        const removed = new Set(chunk);
        applyAndCache((prev) => prev.filter((m) => !removed.has(m.id)));
      }
      return { success: true, deletedIds };
    } catch (err) {
      error.set(messageFor(err, 'Failed to delete memories'));
      return { success: false, deletedIds };
    }
  };

  const toggleVisibility = (id: string, visibility: MemoryVisibility): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = memories.peek().find((m) => m.id === id);
      applyAndCache((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, visibility, updated_at: new Date().toISOString() } : m,
        ),
      );

      try {
        await updateMemoryVisibility(id, visibility);
        error.set(null);
        return true;
      } catch (err) {
        if (previous) {
          applyAndCache((prev) => prev.map((m) => (m.id === id ? previous : m)));
        }
        error.set(messageFor(err, 'Failed to update visibility'));
        return false;
      }
    });

  const acceptMemory = (id: string): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = memories.peek().find((m) => m.id === id);
      applyAndCache((prev) =>
        prev.map((m) => (m.id === id ? { ...m, reviewed: true, user_review: true } : m)),
      );

      try {
        await reviewMemory(id, true);
        error.set(null);
        return true;
      } catch (err) {
        if (previous) {
          applyAndCache((prev) => prev.map((m) => (m.id === id ? previous : m)));
        }
        error.set(messageFor(err, 'Failed to accept memory'));
        return false;
      }
    });

  const rejectMemory = (id: string): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = memories.peek();
      applyAndCache((prev) => prev.filter((m) => m.id !== id));

      try {
        await reviewMemory(id, false);
        error.set(null);
        return true;
      } catch (err) {
        memories.set(previous);
        updateCacheMemories(cacheKey(), () => previous);
        error.set(messageFor(err, 'Failed to reject memory'));
        return false;
      }
    });

  return {
    memories,
    loading,
    error,
    hasMore,
    activeCategories,
    loadInitial,
    loadMore,
    refresh,
    reloadAfterInvalidation,
    setCategories,
    addMemory,
    editMemory,
    removeMemory,
    removeMemories,
    toggleVisibility,
    acceptMemory,
    rejectMemory,
  };
}

export function useMemories(options: UseMemoriesOptions = {}): UseMemoriesReturn {
  const { limit = 25 } = options;
  const initialCategories = options.categories || [];
  const categoriesKey = JSON.stringify(initialCategories);

  const store = useMemo(
    () => createMemoriesStore(limit, initialCategories),
    // Only recreate when the caller-supplied filter identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [limit, categoriesKey],
  );

  useEffect(() => {
    void store.loadInitial();
  }, [store]);

  useEffect(() => {
    return onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.memories) {
        void store.reloadAfterInvalidation();
      }
    });
  }, [store]);

  const memoriesList = useSignalValue(store.memories);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);
  const hasMore = useSignalValue(store.hasMore);
  const activeCategories = useSignalValue(store.activeCategories);

  return {
    memories: memoriesList,
    loading,
    error,
    hasMore,
    loadMore: useCallback(() => store.loadMore(), [store]),
    refresh: useCallback(() => store.refresh(), [store]),
    addMemory: useCallback(
      (content: string, visibility?: MemoryVisibility) => store.addMemory(content, visibility),
      [store],
    ),
    editMemory: useCallback(
      (id: string, content: string) => store.editMemory(id, content),
      [store],
    ),
    removeMemory: useCallback((id: string) => store.removeMemory(id), [store]),
    removeMemories: useCallback((ids: string[]) => store.removeMemories(ids), [store]),
    toggleVisibility: useCallback(
      (id: string, visibility: MemoryVisibility) => store.toggleVisibility(id, visibility),
      [store],
    ),
    acceptMemory: useCallback((id: string) => store.acceptMemory(id), [store]),
    rejectMemory: useCallback((id: string) => store.rejectMemory(id), [store]),
    setCategories: useCallback(
      (categories: MemoryCategory[]) => store.setCategories(categories),
      [store],
    ),
    activeCategories,
  };
}
