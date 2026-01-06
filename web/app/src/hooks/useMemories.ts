'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { Memory, MemoryCategory, MemoryVisibility } from '@/types/conversation';
import {
  getMemories,
  createMemory,
  updateMemoryContent,
  updateMemoryVisibility,
  deleteMemory,
  reviewMemory,
} from '@/lib/api';
import {
  getCache,
  setCache,
  updateCache,
  onCacheInvalidation,
  invalidationPatterns,
  CACHE_TTL,
  cacheKeys,
} from '@/lib/cache';

export interface UseMemoriesOptions {
  categories?: MemoryCategory[];
  limit?: number;
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
  toggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  acceptMemory: (id: string) => Promise<boolean>;
  rejectMemory: (id: string) => Promise<boolean>;
  setCategories: (categories: MemoryCategory[]) => void;
  activeCategories: MemoryCategory[];
}

// Cache entry structure
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

function setToCache(key: string, memories: Memory[], offset: number, hasMore: boolean): void {
  setCache<CacheEntry>(key, { memories, offset, hasMore }, CACHE_TTL.MEDIUM);
}

function updateCacheMemories(key: string, updater: (memories: Memory[]) => Memory[]): void {
  updateCache<CacheEntry>(key, (entry) => ({
    ...entry,
    memories: updater(entry.memories),
  }));
}

function isCacheStale(key: string): boolean {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.isStale : true;
}

export function useMemories(options: UseMemoriesOptions = {}): UseMemoriesReturn {
  const { limit = 25 } = options;

  const [activeCategories, setActiveCategories] = useState<MemoryCategory[]>(
    options.categories || []
  );

  // Get cache key for current categories
  const cacheKey = getCacheKey(activeCategories);
  const cachedEntry = getFromCache(cacheKey);

  // Initialize state from cache if available
  const [memories, setMemories] = useState<Memory[]>(cachedEntry?.memories || []);
  const [loading, setLoading] = useState(!cachedEntry); // Only show loading if no cache
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cachedEntry?.hasMore ?? true);

  // Use ref for offset to avoid dependency issues
  const offsetRef = useRef(cachedEntry?.offset || 0);
  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);
  // Track if initial fetch is done
  const initializedRef = useRef(false);

  // Core fetch function
  const doFetch = useCallback(async (
    categories: MemoryCategory[],
    currentOffset: number
  ): Promise<Memory[]> => {
    const result = await getMemories({
      limit,
      offset: currentOffset,
      categories: categories.length > 0 ? categories : undefined,
    });
    return result;
  }, [limit]);

  // Initial load - check cache first
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const key = getCacheKey(activeCategories);
    const cached = getFromCache(key);

    // If we have fresh cache, use it and skip fetch
    if (cached && !isCacheStale(key)) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      offsetRef.current = cached.offset;
      setLoading(false);
      return;
    }

    // If we have stale cache, show it but refresh in background
    if (cached) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      offsetRef.current = cached.offset;
      setLoading(false);
      // Don't return - continue to background refresh
    }

    const loadInitial = async () => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      // Only show loading spinner if no cached data
      if (!cached) {
        setLoading(true);
      }
      setError(null);

      try {
        const result = await doFetch(activeCategories, 0);
        setMemories(result);
        offsetRef.current = result.length;
        setHasMore(result.length >= limit);
        // Update cache
        setToCache(key, result, result.length, result.length >= limit);
      } catch (err) {
        // Only set error if we don't have cached data to show
        if (!cached) {
          setError(err instanceof Error ? err.message : 'Failed to load memories');
        }
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    };

    loadInitial();
  }, [doFetch, activeCategories, limit]);

  // Handle category changes (after initial load)
  const prevCategoriesRef = useRef<string>(JSON.stringify(activeCategories));
  useEffect(() => {
    const currentKey = JSON.stringify(activeCategories);
    if (prevCategoriesRef.current === currentKey) return;
    prevCategoriesRef.current = currentKey;

    // Only refetch if already initialized
    if (!initializedRef.current) return;

    const key = getCacheKey(activeCategories);
    const cached = getFromCache(key);

    // If we have cache for this category, use it immediately
    if (cached) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      offsetRef.current = cached.offset;

      // If not stale, we're done
      if (!isCacheStale(key)) {
        return;
      }
      // If stale, continue to background refresh
    }

    const loadForCategories = async () => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      // Only show loading if no cache
      if (!cached) {
        setLoading(true);
      }
      setError(null);

      try {
        const result = await doFetch(activeCategories, 0);
        setMemories(result);
        offsetRef.current = result.length;
        setHasMore(result.length >= limit);
        // Update cache
        setToCache(key, result, result.length, result.length >= limit);
      } catch (err) {
        if (!cached) {
          setError(err instanceof Error ? err.message : 'Failed to load memories');
        }
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    };

    loadForCategories();
  }, [activeCategories, doFetch, limit]);

  // Subscribe to cache invalidation - refetch when memories are modified elsewhere
  useEffect(() => {
    const unsubscribe = onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.memories) {
        // Clear local state and refetch
        const key = getCacheKey(activeCategories);
        const loadFresh = async () => {
          if (fetchingRef.current) return;
          fetchingRef.current = true;
          try {
            const result = await doFetch(activeCategories, 0);
            setMemories(result);
            offsetRef.current = result.length;
            setHasMore(result.length >= limit);
            setToCache(key, result, result.length, result.length >= limit);
          } catch (err) {
            // Silent fail on background refresh
            console.error('Failed to refresh memories after invalidation:', err);
          } finally {
            fetchingRef.current = false;
          }
        };
        loadFresh();
      }
    });
    return unsubscribe;
  }, [activeCategories, doFetch, limit]);

  // Load more (pagination)
  const loadMore = useCallback(async () => {
    if (fetchingRef.current || !hasMore) return;
    fetchingRef.current = true;
    setLoading(true);

    const key = getCacheKey(activeCategories);

    try {
      const result = await doFetch(activeCategories, offsetRef.current);

      setMemories((prev) => {
        // Deduplicate
        const existingIds = new Set(prev.map(m => m.id));
        const newMemories = result.filter(m => !existingIds.has(m.id));
        const updated = [...prev, ...newMemories];
        // Update cache with new memories
        const newOffset = offsetRef.current + result.length;
        const newHasMore = result.length >= limit;
        setToCache(key, updated, newOffset, newHasMore);
        return updated;
      });

      offsetRef.current += result.length;
      setHasMore(result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more memories');
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [activeCategories, doFetch, hasMore, limit]);

  // Refresh
  const refresh = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoading(true);
    setError(null);

    const key = getCacheKey(activeCategories);

    try {
      const result = await doFetch(activeCategories, 0);
      setMemories(result);
      offsetRef.current = result.length;
      setHasMore(result.length >= limit);
      // Update cache
      setToCache(key, result, result.length, result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh memories');
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [activeCategories, doFetch, limit]);

  // Add memory
  const addMemory = useCallback(async (
    content: string,
    visibility: MemoryVisibility = 'public'
  ): Promise<Memory | null> => {
    const key = getCacheKey(activeCategories);
    try {
      const newMemory = await createMemory({ content, visibility, category: 'manual' });
      setMemories((prev) => {
        const updated = [newMemory, ...prev];
        // Update cache
        updateCacheMemories(key, () => updated);
        return updated;
      });
      return newMemory;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create memory');
      return null;
    }
  }, [activeCategories]);

  // Edit memory
  const editMemory = useCallback(async (id: string, content: string): Promise<boolean> => {
    const key = getCacheKey(activeCategories);
    try {
      await updateMemoryContent(id, content);
      const updater = (prev: Memory[]) =>
        prev.map((m) =>
          m.id === id ? { ...m, content, edited: true, updated_at: new Date().toISOString() } : m
        );
      setMemories(updater);
      updateCacheMemories(key, updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update memory');
      return false;
    }
  }, [activeCategories]);

  // Remove memory
  const removeMemory = useCallback(async (id: string): Promise<boolean> => {
    const key = getCacheKey(activeCategories);
    try {
      await deleteMemory(id);
      const updater = (prev: Memory[]) => prev.filter((m) => m.id !== id);
      setMemories(updater);
      updateCacheMemories(key, updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete memory');
      return false;
    }
  }, [activeCategories]);

  // Toggle visibility
  const toggleVisibility = useCallback(async (
    id: string,
    visibility: MemoryVisibility
  ): Promise<boolean> => {
    const key = getCacheKey(activeCategories);
    try {
      await updateMemoryVisibility(id, visibility);
      const updater = (prev: Memory[]) =>
        prev.map((m) =>
          m.id === id ? { ...m, visibility, updated_at: new Date().toISOString() } : m
        );
      setMemories(updater);
      updateCacheMemories(key, updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update visibility');
      return false;
    }
  }, [activeCategories]);

  // Accept memory
  const acceptMemory = useCallback(async (id: string): Promise<boolean> => {
    const key = getCacheKey(activeCategories);
    try {
      await reviewMemory(id, true);
      const updater = (prev: Memory[]) =>
        prev.map((m) =>
          m.id === id ? { ...m, reviewed: true, user_review: true } : m
        );
      setMemories(updater);
      updateCacheMemories(key, updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept memory');
      return false;
    }
  }, [activeCategories]);

  // Reject memory
  const rejectMemory = useCallback(async (id: string): Promise<boolean> => {
    const key = getCacheKey(activeCategories);
    try {
      await reviewMemory(id, false);
      const updater = (prev: Memory[]) => prev.filter((m) => m.id !== id);
      setMemories(updater);
      updateCacheMemories(key, updater);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject memory');
      return false;
    }
  }, [activeCategories]);

  // Set categories
  const setCategories = useCallback((categories: MemoryCategory[]) => {
    setActiveCategories(categories);
    offsetRef.current = 0;
  }, []);

  return {
    memories,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
    addMemory,
    editMemory,
    removeMemory,
    toggleVisibility,
    acceptMemory,
    rejectMemory,
    setCategories,
    activeCategories,
  };
}
