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

// Cache configuration
const CACHE_KEY = 'omi_memories_cache';
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

interface MemoriesCache {
  memories: Memory[];
  timestamp: number;
  categoriesKey: string;
}

function getCacheKey(categories: MemoryCategory[]): string {
  return categories.length > 0 ? categories.sort().join(',') : 'all';
}

function getCache(categoriesKey: string): MemoriesCache | null {
  try {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const data: MemoriesCache = JSON.parse(cached);
    if (data.categoriesKey !== categoriesKey) return null;
    if (Date.now() - data.timestamp > CACHE_TTL_MS) return null;

    return data;
  } catch {
    return null;
  }
}

function setCache(memories: Memory[], categoriesKey: string): void {
  try {
    const data: MemoriesCache = {
      memories,
      timestamp: Date.now(),
      categoriesKey,
    };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // Ignore storage errors
  }
}

export interface UseMemoriesOptions {
  categories?: MemoryCategory[];
  limit?: number;
}

export interface UseMemoriesReturn {
  memories: Memory[];
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  // Actions
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
  addMemory: (content: string, visibility?: MemoryVisibility) => Promise<Memory | null>;
  editMemory: (id: string, content: string) => Promise<boolean>;
  removeMemory: (id: string) => Promise<boolean>;
  toggleVisibility: (id: string, visibility: MemoryVisibility) => Promise<boolean>;
  acceptMemory: (id: string) => Promise<boolean>;
  rejectMemory: (id: string) => Promise<boolean>;
  // Filters
  setCategories: (categories: MemoryCategory[]) => void;
  activeCategories: MemoryCategory[];
}

export function useMemories(options: UseMemoriesOptions = {}): UseMemoriesReturn {
  const { limit = 50 } = options;

  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [activeCategories, setActiveCategories] = useState<MemoryCategory[]>(
    options.categories || []
  );

  const initialFetchDone = useRef(false);
  const cacheLoaded = useRef(false);

  // Fetch memories
  const fetchMemories = useCallback(async (reset = false, isBackground = false) => {
    try {
      if (!isBackground) {
        setLoading(true);
      }
      setError(null);

      const currentOffset = reset ? 0 : offset;
      const result = await getMemories({
        limit,
        offset: currentOffset,
        categories: activeCategories.length > 0 ? activeCategories : undefined,
      });

      if (reset) {
        setMemories(result);
        setOffset(result.length);
        // Update cache with fresh data
        setCache(result, getCacheKey(activeCategories));
      } else {
        setMemories((prev) => {
          const updated = [...prev, ...result];
          // Update cache with all loaded memories
          setCache(updated, getCacheKey(activeCategories));
          return updated;
        });
        setOffset((prev) => prev + result.length);
      }

      setHasMore(result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memories');
    } finally {
      setLoading(false);
    }
  }, [limit, offset, activeCategories]);

  // Initial fetch with cache
  useEffect(() => {
    if (!initialFetchDone.current) {
      initialFetchDone.current = true;

      // Try to load from cache first
      const categoriesKey = getCacheKey(activeCategories);
      const cached = getCache(categoriesKey);

      if (cached && !cacheLoaded.current) {
        cacheLoaded.current = true;
        setMemories(cached.memories);
        setOffset(cached.memories.length);
        setHasMore(cached.memories.length >= limit);
        setLoading(false);

        // Fetch fresh data in background
        fetchMemories(true, true);
      } else {
        fetchMemories(true);
      }
    }
  }, [fetchMemories, activeCategories, limit]);

  // Refetch when categories change
  useEffect(() => {
    if (initialFetchDone.current) {
      // Check cache for new categories first
      const categoriesKey = getCacheKey(activeCategories);
      const cached = getCache(categoriesKey);

      if (cached) {
        setMemories(cached.memories);
        setOffset(cached.memories.length);
        setHasMore(cached.memories.length >= limit);
        // Still fetch fresh in background
        fetchMemories(true, true);
      } else {
        fetchMemories(true);
      }
    }
  }, [activeCategories]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load more
  const loadMore = useCallback(async () => {
    if (!loading && hasMore) {
      await fetchMemories(false);
    }
  }, [loading, hasMore, fetchMemories]);

  // Refresh - always fetch fresh, ignore cache
  const refresh = useCallback(async () => {
    initialFetchDone.current = true;
    setOffset(0);
    await fetchMemories(true, false);
  }, [fetchMemories]);

  // Add memory
  const addMemory = useCallback(async (
    content: string,
    visibility: MemoryVisibility = 'public'
  ): Promise<Memory | null> => {
    try {
      const newMemory = await createMemory({ content, visibility, category: 'manual' });
      setMemories((prev) => [newMemory, ...prev]);
      return newMemory;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create memory');
      return null;
    }
  }, []);

  // Edit memory
  const editMemory = useCallback(async (
    id: string,
    content: string
  ): Promise<boolean> => {
    try {
      await updateMemoryContent(id, content);
      setMemories((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, content, edited: true, updated_at: new Date().toISOString() } : m
        )
      );
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update memory');
      return false;
    }
  }, []);

  // Remove memory
  const removeMemory = useCallback(async (id: string): Promise<boolean> => {
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete memory');
      return false;
    }
  }, []);

  // Toggle visibility
  const toggleVisibility = useCallback(async (
    id: string,
    visibility: MemoryVisibility
  ): Promise<boolean> => {
    try {
      await updateMemoryVisibility(id, visibility);
      setMemories((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, visibility, updated_at: new Date().toISOString() } : m
        )
      );
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update visibility');
      return false;
    }
  }, []);

  // Accept memory
  const acceptMemory = useCallback(async (id: string): Promise<boolean> => {
    try {
      await reviewMemory(id, true);
      setMemories((prev) =>
        prev.map((m) =>
          m.id === id ? { ...m, reviewed: true, user_review: true } : m
        )
      );
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept memory');
      return false;
    }
  }, []);

  // Reject memory
  const rejectMemory = useCallback(async (id: string): Promise<boolean> => {
    try {
      await reviewMemory(id, false);
      // Remove rejected memories from the list
      setMemories((prev) => prev.filter((m) => m.id !== id));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject memory');
      return false;
    }
  }, []);

  // Set categories filter
  const setCategories = useCallback((categories: MemoryCategory[]) => {
    setActiveCategories(categories);
    setOffset(0);
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
