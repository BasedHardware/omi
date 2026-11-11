'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import type { Memory, MemoryCategory, MemoryVisibility } from '@/types/conversation';
import {
  getMemoriesPage,
  createMemory,
  updateMemoryContent,
  updateMemoryVisibility,
  deleteMemory,
  deleteMemoriesBatch,
  reviewMemory,
} from '@/lib/api';
import {
  getCache,
  setCache,
  updateCache,
  deleteCachePattern,
  onCacheInvalidation,
  invalidationPatterns,
  CACHE_TTL,
  cacheKeys,
  getMemoryBackendScope,
  memoryCacheScopeKey,
  type MemoryCacheScope,
} from '@/lib/cache';
import {
  getCachedMemories,
  cacheMemories,
  invalidateCache as invalidateMemoryCache,
} from '@/lib/indexeddb';

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
  /** True when the server could not complete the bounded provider read. */
  truncated: boolean;
  loadMore: () => Promise<void>;
  /** Returns true only after a canonical network refresh completed. */
  refresh: (throwOnError?: boolean) => Promise<boolean>;
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

// Cache entry structure
interface CacheEntry {
  memories: Memory[];
  offset: number;
  nextCursor: string | null;
  hasMore: boolean;
  truncated: boolean;
}

function getCacheKey(
  categories: MemoryCategory[],
  scope: MemoryCacheScope | null,
): string | null {
  if (!scope) return null;
  return cacheKeys.memories(categories.length === 0 ? [] : [...categories].sort(), scope);
}

function getFromCache(key: string): CacheEntry | null {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.data : null;
}

function setToCache(
  key: string,
  memories: Memory[],
  offset: number,
  nextCursor: string | null,
  hasMore: boolean,
  truncated: boolean,
): void {
  setCache<CacheEntry>(
    key,
    { memories, offset, nextCursor, hasMore, truncated },
    CACHE_TTL.MEDIUM,
  );
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

export function useMemories(options: UseMemoriesOptions = {}): UseMemoriesReturn {
  const { limit = 25 } = options;
  const { user, loading: authLoading } = useAuth();
  const backendScope = getMemoryBackendScope();
  // AuthProvider can briefly retain a user while auth is being resolved. Do not
  // read a persisted cache until both the owner and auth state are settled.
  const memoryCacheScope: MemoryCacheScope | null =
    !authLoading && user ? { ownerId: user.uid, backendScope } : null;
  const scopeKey = memoryCacheScope ? memoryCacheScopeKey(memoryCacheScope) : null;

  const [activeCategories, setActiveCategories] = useState<MemoryCategory[]>(
    options.categories || [],
  );

  // Get cache key for current categories
  const cacheKey = getCacheKey(activeCategories, memoryCacheScope);
  const cachedEntry = cacheKey ? getFromCache(cacheKey) : null;

  // Initialize state from cache if available
  const [memories, setMemories] = useState<Memory[]>(cachedEntry?.memories || []);
  const [loading, setLoading] = useState(!cachedEntry); // Only show loading if no cache
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cachedEntry?.hasMore ?? true);
  const [truncated, setTruncated] = useState(cachedEntry?.truncated ?? false);
  // Bumped whenever a network fetch releases the fetching lock, so a
  // view/category change that arrived mid-fetch re-runs once idle.
  const [fetchIdleTick, setFetchIdleTick] = useState(0);

  // Use ref for offset to avoid dependency issues
  const offsetRef = useRef(cachedEntry?.offset || 0);
  const cursorRef = useRef<string | null>(cachedEntry?.nextCursor || null);
  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);
  // In-flight canonical refresh, shared with concurrent callers (see refresh).
  const refreshInFlightRef = useRef<Promise<boolean> | null>(null);
  // Track if initial fetch is done
  const initializedRef = useRef(false);
  const scopeKeyRef = useRef<string | null>(null);
  const scopeGenerationRef = useRef(0);
  const activeStateScopeRef = useRef<string | null>(null);
  const previousScopeRef = useRef<MemoryCacheScope | null>(null);
  const currentScopeRef = useRef<MemoryCacheScope | null>(null);
  currentScopeRef.current = memoryCacheScope;
  // Latest categories query, assigned every render so an in-flight
  // request can detect the visible query moved on before its response lands.
  const latestQueryRef = useRef('');
  latestQueryRef.current = JSON.stringify(activeCategories);
  const captureScopeGeneration = () => {
    const requestScopeKey = scopeKeyRef.current;
    const requestGeneration = scopeGenerationRef.current;
    return () =>
      Boolean(requestScopeKey) &&
      scopeKeyRef.current === requestScopeKey &&
      scopeGenerationRef.current === requestGeneration;
  };

  // A scope transition is a new data session. Clear visible state before any
  // new owner/backend request can resolve, and invalidate the old session's
  // in-flight writes by advancing the generation token.
  useEffect(() => {
    if (scopeKeyRef.current === scopeKey) return;

    const previousScope = previousScopeRef.current;
    scopeKeyRef.current = scopeKey;
    previousScopeRef.current = memoryCacheScope;
    scopeGenerationRef.current += 1;
    activeStateScopeRef.current = scopeKey;
    // A new session abandons any in-flight canonical refresh from the old one.
    fetchingRef.current = false;
    refreshInFlightRef.current = null;
    initializedRef.current = false;
    offsetRef.current = 0;
    cursorRef.current = null;
    setMemories([]);
    setLoading(Boolean(scopeKey));
    setError(null);
    setHasMore(true);
    setTruncated(false);

    if (previousScope) {
      deleteCachePattern(invalidationPatterns.memories, previousScope);
      void invalidateMemoryCache(previousScope);
    }
  }, [memoryCacheScope, scopeKey]);

  // Core fetch function
  const doFetch = useCallback(
    async (
      categories: MemoryCategory[],
      currentOffset: number,
      cursor: string | null = null,
    ) => {
      return getMemoriesPage({
        limit,
        offset: currentOffset,
        cursor: cursor || undefined,
        categories: categories.length > 0 ? categories : undefined,
      });
    },
    [limit],
  );

  // Initial load - check cache first (memory → IndexedDB → network)
  useEffect(() => {
    if (!scopeKey || authLoading || !memoryCacheScope || !cacheKey) return;
    if (initializedRef.current) return;
    initializedRef.current = true;

    const requestScopeKey = scopeKey;
    const requestGeneration = scopeGenerationRef.current;
    const requestQuery = JSON.stringify(activeCategories);
    const isCurrentRequest = () =>
      scopeKeyRef.current === requestScopeKey &&
      scopeGenerationRef.current === requestGeneration;
    // Fence by query as well as scope: a view/category change mid-request
    // must not apply the old query's page to the newly selected one.
    const isQueryCurrent = () => latestQueryRef.current === requestQuery;

    const key = cacheKey;
    const cached = getFromCache(key);

    // If we have fresh in-memory cache, use it and skip fetch
    if (cached && !isCacheStale(key)) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      setTruncated(cached.truncated);
      offsetRef.current = cached.offset;
      cursorRef.current = cached.nextCursor;
      setLoading(false);
      return;
    }

    // If we have stale in-memory cache, show it but refresh in background
    if (cached) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      setTruncated(cached.truncated);
      offsetRef.current = cached.offset;
      cursorRef.current = cached.nextCursor;
      setLoading(false);
      // Don't return - continue to background refresh
    }

    const loadInitial = async () => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      // Try IndexedDB first if no in-memory cache
      if (!cached) {
        const indexedDBMemories = await getCachedMemories(memoryCacheScope);
        if (!isCurrentRequest() || !isQueryCurrent()) {
          // A same-scope query change can abandon this warmup before the
          // network fetch's finally block. Release the shared fetch lock so
          // the latest query can retry on the next idle tick.
          if (isCurrentRequest()) {
            fetchingRef.current = false;
            setFetchIdleTick((tick) => tick + 1);
          }
          return;
        }
        if (indexedDBMemories && indexedDBMemories.length > 0) {
          console.log('[useMemories] Loaded from IndexedDB');
          setMemories(indexedDBMemories);
          offsetRef.current = indexedDBMemories.length;
          setHasMore(indexedDBMemories.length >= limit);
          // Also update in-memory cache
          setToCache(
            key,
            indexedDBMemories,
            indexedDBMemories.length,
            null,
            indexedDBMemories.length >= limit,
            false,
          );
          setLoading(false);
          // Continue to background refresh to get latest data
        } else {
          // No cache at all, show loading
          setLoading(true);
        }
      } else {
        // Already showing stale in-memory cache, don't show loading
        setLoading(false);
      }

      setError(null);

      try {
        const page = await doFetch(activeCategories, 0);
        if (!isCurrentRequest() || !isQueryCurrent()) return;
        const pageHasMore =
          Boolean(page.nextCursor) || (!page.truncated && page.memories.length >= limit);
        setMemories(page.memories);
        offsetRef.current = page.memories.length;
        cursorRef.current = page.nextCursor;
        setHasMore(pageHasMore);
        setTruncated(page.truncated);
        // Update both caches
        setToCache(
          key,
          page.memories,
          page.memories.length,
          page.nextCursor,
          pageHasMore,
          page.truncated,
        );
        await cacheMemories(page.memories, memoryCacheScope);
        if (!isCurrentRequest() || !isQueryCurrent()) return;
      } catch (err) {
        if (!isCurrentRequest() || !isQueryCurrent()) return;
        // Check if we have any cached data to show
        let hasAnyCachedData = !!cached;
        if (!hasAnyCachedData) {
          try {
            const indexedDbMemories = await getCachedMemories(memoryCacheScope);
            if (!isCurrentRequest() || !isQueryCurrent()) return;
            hasAnyCachedData = !!indexedDbMemories;
          } catch {
            // If reading from IndexedDB fails, don't mask the original error
          }
        }

        const baseMessage =
          err instanceof Error ? err.message : 'Failed to load memories';
        if (hasAnyCachedData) {
          // Show that refresh failed but cached data is available
          setError(`${baseMessage} (showing cached data)`);
        } else {
          setError(baseMessage);
        }
      } finally {
        if (isCurrentRequest()) {
          setLoading(false);
          fetchingRef.current = false;
          setFetchIdleTick((tick) => tick + 1);
        }
      }
    };

    loadInitial();
  }, [
    authLoading,
    cacheKey,
    doFetch,
    activeCategories,
    limit,
    memoryCacheScope,
    scopeKey,
  ]);

  // Handle category changes (after initial load)
  const prevQueryRef = useRef<string>(JSON.stringify(activeCategories));
  useEffect(() => {
    if (!scopeKey || authLoading || !memoryCacheScope) return;
    const currentQuery = JSON.stringify(activeCategories);
    if (prevQueryRef.current === currentQuery) return;

    // Only refetch if already initialized
    if (!initializedRef.current) return;

    const key = getCacheKey(activeCategories, memoryCacheScope);
    if (!key) return;
    const cached = getFromCache(key);

    // If we have cache for this category, use it immediately
    if (cached) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      setTruncated(cached.truncated);
      offsetRef.current = cached.offset;
      cursorRef.current = cached.nextCursor;

      // If not stale, we're done
      if (!isCacheStale(key)) {
        // No fetch runs here, so clear the error left by the previous categories
        setError(null);
        prevQueryRef.current = currentQuery;
        return;
      }
      // If stale, continue to background refresh
    }

    // Another query's fetch can still hold the lock. Leave the query
    // unconsumed; the fetchIdleTick bump when that fetch goes idle re-runs
    // this effect and fetches the latest view then.
    if (fetchingRef.current) return;
    prevQueryRef.current = currentQuery;

    const loadForCategories = async () => {
      fetchingRef.current = true;
      const requestScopeKey = scopeKey;
      const requestGeneration = scopeGenerationRef.current;
      const requestQuery = currentQuery;
      const isCurrentRequest = () =>
        scopeKeyRef.current === requestScopeKey &&
        scopeGenerationRef.current === requestGeneration;
      const isQueryCurrent = () => latestQueryRef.current === requestQuery;

      // Only show loading if no cache
      if (!cached) {
        setLoading(true);
      }
      setError(null);

      try {
        const page = await doFetch(activeCategories, 0);
        if (!isCurrentRequest() || !isQueryCurrent()) return;
        const pageHasMore =
          Boolean(page.nextCursor) || (!page.truncated && page.memories.length >= limit);
        setMemories(page.memories);
        offsetRef.current = page.memories.length;
        cursorRef.current = page.nextCursor;
        setHasMore(pageHasMore);
        setTruncated(page.truncated);
        // Update cache
        setToCache(
          key,
          page.memories,
          page.memories.length,
          page.nextCursor,
          pageHasMore,
          page.truncated,
        );
      } catch (err) {
        if (isCurrentRequest() && isQueryCurrent() && !cached) {
          setError(err instanceof Error ? err.message : 'Failed to load memories');
        }
      } finally {
        if (isCurrentRequest()) {
          setLoading(false);
          fetchingRef.current = false;
          setFetchIdleTick((tick) => tick + 1);
        }
      }
    };

    loadForCategories();
  }, [
    activeCategories,
    authLoading,
    doFetch,
    fetchIdleTick,
    limit,
    memoryCacheScope,
    scopeKey,
  ]);

  // Load more (pagination)
  const loadMore = useCallback(async () => {
    const scope = currentScopeRef.current;
    const requestedScopeKey = scopeKeyRef.current;
    if (!scope || !requestedScopeKey || fetchingRef.current || !hasMore) return;
    fetchingRef.current = true;
    setLoading(true);

    const key = getCacheKey(activeCategories, scope);
    if (!key) {
      fetchingRef.current = false;
      setFetchIdleTick((tick) => tick + 1);
      setLoading(false);
      return;
    }
    const requestGeneration = scopeGenerationRef.current;
    const requestQuery = latestQueryRef.current;
    const isCurrentRequest = () =>
      scopeKeyRef.current === requestedScopeKey &&
      scopeGenerationRef.current === requestGeneration;
    const isQueryCurrent = () => latestQueryRef.current === requestQuery;

    try {
      const page = await doFetch(activeCategories, offsetRef.current, cursorRef.current);
      if (!isCurrentRequest() || !isQueryCurrent()) return;
      const pageHasMore =
        Boolean(page.nextCursor) || (!page.truncated && page.memories.length >= limit);

      setMemories((prev) => {
        // Deduplicate
        const existingIds = new Set(prev.map((m) => m.id));
        const newMemories = page.memories.filter((m) => !existingIds.has(m.id));
        const updated = [...prev, ...newMemories];
        // Update cache with new memories
        const newOffset = offsetRef.current + page.memories.length;
        setToCache(key, updated, newOffset, page.nextCursor, pageHasMore, page.truncated);
        return updated;
      });

      offsetRef.current += page.memories.length;
      cursorRef.current = page.nextCursor;
      setHasMore(pageHasMore);
      setTruncated(page.truncated);
    } catch (err) {
      if (isCurrentRequest() && isQueryCurrent()) {
        setError(err instanceof Error ? err.message : 'Failed to load more memories');
      }
    } finally {
      if (isCurrentRequest()) {
        setLoading(false);
        fetchingRef.current = false;
        setFetchIdleTick((tick) => tick + 1);
      }
    }
  }, [activeCategories, doFetch, hasMore, limit]);

  // Refresh
  const refresh = useCallback(
    async (throwOnError = false) => {
      // Single-flight canonical refresh: a mutation's synchronous cache
      // invalidation starts this fetch before the mutation's own canonical
      // re-read runs, so concurrent callers join the in-flight request
      // instead of being told the refresh failed.
      if (refreshInFlightRef.current) return refreshInFlightRef.current;
      const scope = currentScopeRef.current;
      const requestedScopeKey = scopeKeyRef.current;
      if (!scope || !requestedScopeKey || fetchingRef.current) return false;
      fetchingRef.current = true;
      setLoading(true);
      setError(null);

      const key = getCacheKey(activeCategories, scope);
      if (!key) {
        fetchingRef.current = false;
        setFetchIdleTick((tick) => tick + 1);
        setLoading(false);
        return false;
      }
      const requestGeneration = scopeGenerationRef.current;
      const requestQuery = latestQueryRef.current;
      const isCurrentRequest = () =>
        scopeKeyRef.current === requestedScopeKey &&
        scopeGenerationRef.current === requestGeneration;
      const isQueryCurrent = () => latestQueryRef.current === requestQuery;

      const holder: { promise: Promise<boolean> | null } = { promise: null };
      holder.promise = (async () => {
        try {
          const page = await doFetch(activeCategories, 0);
          if (!isCurrentRequest() || !isQueryCurrent()) return false;
          const pageHasMore =
            Boolean(page.nextCursor) ||
            (!page.truncated && page.memories.length >= limit);
          setMemories(page.memories);
          offsetRef.current = page.memories.length;
          cursorRef.current = page.nextCursor;
          setHasMore(pageHasMore);
          setTruncated(page.truncated);
          // Update cache
          setToCache(
            key,
            page.memories,
            page.memories.length,
            page.nextCursor,
            pageHasMore,
            page.truncated,
          );
          return true;
        } catch (err) {
          if (isCurrentRequest() && isQueryCurrent()) {
            setError(err instanceof Error ? err.message : 'Failed to refresh memories');
            if (throwOnError) throw err;
          }
          return false;
        } finally {
          if (isCurrentRequest()) {
            setLoading(false);
            fetchingRef.current = false;
            setFetchIdleTick((tick) => tick + 1);
          }
          if (refreshInFlightRef.current === holder.promise)
            refreshInFlightRef.current = null;
        }
      })();
      refreshInFlightRef.current = holder.promise;
      return holder.promise;
    },
    [activeCategories, doFetch, limit],
  );

  // Subscribe to cache invalidation - refetch when memories are modified elsewhere
  useEffect(() => {
    if (!scopeKey || authLoading || !memoryCacheScope) return;
    const unsubscribe = onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.memories) {
        // Mutations invalidate synchronously — api.ts fires these listeners
        // before its awaiting caller resumes — so a committed use-feedback
        // POST starts this canonical refresh and then joins it through
        // refresh's single flight instead of racing it.
        void refresh();
      }
    });
    return unsubscribe;
  }, [authLoading, memoryCacheScope, refresh, scopeKey]);

  // Add memory
  const addMemory = useCallback(
    async (
      content: string,
      visibility: MemoryVisibility = 'public',
    ): Promise<Memory | null> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return null;
      const isCurrentRequest = captureScopeGeneration();
      try {
        const newMemory = await createMemory({ content, visibility, category: 'manual' });
        if (!isCurrentRequest()) return null;
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
    },
    [activeCategories],
  );

  // Edit memory
  const editMemory = useCallback(
    async (id: string, content: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return false;
      const isCurrentRequest = captureScopeGeneration();
      try {
        await updateMemoryContent(id, content);
        if (!isCurrentRequest()) return false;
        const updater = (prev: Memory[]) =>
          prev.map((m) =>
            m.id === id
              ? { ...m, content, edited: true, updated_at: new Date().toISOString() }
              : m,
          );
        setMemories(updater);
        updateCacheMemories(key, updater);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update memory');
        return false;
      }
    },
    [activeCategories],
  );

  // Remove memory
  const removeMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return false;
      const isCurrentRequest = captureScopeGeneration();
      try {
        await deleteMemory(id);
        if (!isCurrentRequest()) return false;
        const updater = (prev: Memory[]) => prev.filter((m) => m.id !== id);
        setMemories(updater);
        updateCacheMemories(key, updater);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete memory');
        return false;
      }
    },
    [activeCategories],
  );

  // Remove multiple memories via the batch API. IDs are sent in chunks of 100 (the
  // server's per-request cap) and each successful chunk is applied to the UI
  // immediately, so a later chunk failure can never leave already-deleted items
  // visible. Returns success only when every chunk succeeded; on partial failure the
  // confirmed-deleted IDs are surfaced via deletedIds so callers can drop them from
  // any selection they keep for retry (otherwise a retry would re-send IDs the server
  // already removed and trip the all-or-nothing 404).
  const removeMemories = useCallback(
    async (ids: string[]): Promise<RemoveMemoriesResult> => {
      if (ids.length === 0) return { success: true, deletedIds: [] };
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return { success: false, deletedIds: [] };
      const isCurrentRequest = captureScopeGeneration();
      const CHUNK_SIZE = 100;
      const deletedIds: string[] = [];
      try {
        for (let i = 0; i < ids.length; i += CHUNK_SIZE) {
          const chunk = ids.slice(i, i + CHUNK_SIZE);
          await deleteMemoriesBatch(chunk);
          if (!isCurrentRequest()) return { success: false, deletedIds };
          deletedIds.push(...chunk);
          const removed = new Set(chunk);
          const updater = (prev: Memory[]) => prev.filter((m) => !removed.has(m.id));
          setMemories(updater);
          updateCacheMemories(key, updater);
        }
        return { success: true, deletedIds };
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete memories');
        return { success: false, deletedIds };
      }
    },
    [activeCategories],
  );

  // Toggle visibility
  const toggleVisibility = useCallback(
    async (id: string, visibility: MemoryVisibility): Promise<boolean> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return false;
      const isCurrentRequest = captureScopeGeneration();
      try {
        await updateMemoryVisibility(id, visibility);
        if (!isCurrentRequest()) return false;
        const updater = (prev: Memory[]) =>
          prev.map((m) =>
            m.id === id ? { ...m, visibility, updated_at: new Date().toISOString() } : m,
          );
        setMemories(updater);
        updateCacheMemories(key, updater);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update visibility');
        return false;
      }
    },
    [activeCategories],
  );

  // Accept memory
  const acceptMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return false;
      const isCurrentRequest = captureScopeGeneration();
      try {
        await reviewMemory(id, true);
        if (!isCurrentRequest()) return false;
        const updater = (prev: Memory[]) =>
          prev.map((m) =>
            m.id === id ? { ...m, reviewed: true, user_review: true } : m,
          );
        setMemories(updater);
        updateCacheMemories(key, updater);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to accept memory');
        return false;
      }
    },
    [activeCategories],
  );

  // Reject memory
  const rejectMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, currentScopeRef.current);
      if (!key) return false;
      const isCurrentRequest = captureScopeGeneration();
      try {
        await reviewMemory(id, false);
        if (!isCurrentRequest()) return false;
        const updater = (prev: Memory[]) => prev.filter((m) => m.id !== id);
        setMemories(updater);
        updateCacheMemories(key, updater);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to reject memory');
        return false;
      }
    },
    [activeCategories],
  );

  // Set categories
  const setCategories = useCallback((categories: MemoryCategory[]) => {
    setActiveCategories(categories);
    offsetRef.current = 0;
    cursorRef.current = null;
  }, []);

  const scopeIsActive =
    Boolean(scopeKey) && !authLoading && activeStateScopeRef.current === scopeKey;

  return {
    memories: scopeIsActive ? memories : [],
    loading: scopeIsActive ? loading : Boolean(scopeKey),
    error: scopeIsActive ? error : null,
    hasMore: scopeIsActive ? hasMore : true,
    truncated: scopeIsActive ? truncated : false,
    loadMore,
    refresh,
    addMemory,
    editMemory,
    removeMemory,
    removeMemories,
    toggleVisibility,
    acceptMemory,
    rejectMemory,
    setCategories,
    activeCategories,
  };
}
