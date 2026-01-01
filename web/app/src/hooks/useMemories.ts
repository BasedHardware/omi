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

  // Fetch memories
  const fetchMemories = useCallback(async (reset = false) => {
    try {
      setLoading(true);
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
      } else {
        setMemories((prev) => [...prev, ...result]);
        setOffset((prev) => prev + result.length);
      }

      setHasMore(result.length >= limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memories');
    } finally {
      setLoading(false);
    }
  }, [limit, offset, activeCategories]);

  // Initial fetch
  useEffect(() => {
    if (!initialFetchDone.current) {
      initialFetchDone.current = true;
      fetchMemories(true);
    }
  }, [fetchMemories]);

  // Refetch when categories change
  useEffect(() => {
    if (initialFetchDone.current) {
      fetchMemories(true);
    }
  }, [activeCategories]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load more
  const loadMore = useCallback(async () => {
    if (!loading && hasMore) {
      await fetchMemories(false);
    }
  }, [loading, hasMore, fetchMemories]);

  // Refresh
  const refresh = useCallback(async () => {
    initialFetchDone.current = true;
    setOffset(0);
    await fetchMemories(true);
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
