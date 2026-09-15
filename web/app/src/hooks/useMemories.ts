'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import type { Memory, MemoryCategory, MemoryVisibility } from '@/types/conversation';
import {
  getMemoriesPage,
  type MemoryView,
  type MemoryUseAction,
  createMemory,
  updateMemoryContent,
  updateMemoryVisibility,
  setMemoryUse as setMemoryUseRequest,
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
  view?: MemoryView;
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
  /** Null means the server did not advertise the beta belief capability. */
  beliefEnabled: boolean | null;
  memoryView: MemoryView;
  setMemoryView: (view: MemoryView) => void;
  setMemoryUse: (id: string, action: MemoryUseAction) => Promise<boolean>;
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
  beliefEnabled?: boolean | null;
}

function getCacheKey(
  categories: MemoryCategory[],
  view: MemoryView,
  scope: MemoryCacheScope | null,
): string | null {
  if (!scope) return null;
  return cacheKeys.memories(
    categories.length === 0 ? [] : [...categories].sort(),
    view,
    scope,
  );
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
  beliefEnabled: boolean | null,
): void {
  setCache<CacheEntry>(
    key,
    { memories, offset, nextCursor, hasMore, truncated, beliefEnabled },
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

function createFeedbackId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  // Keep the request contract UUID-shaped in older browsers and test runners.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === 'x' ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
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
  const [memoryView, setMemoryView] = useState<MemoryView>(options.view || 'useful_now');

  // Get cache key for current categories
  const cacheKey = getCacheKey(activeCategories, memoryView, memoryCacheScope);
  const cachedEntry = cacheKey ? getFromCache(cacheKey) : null;

  // Initialize state from cache if available
  const [memories, setMemories] = useState<Memory[]>(cachedEntry?.memories || []);
  const [loading, setLoading] = useState(!cachedEntry); // Only show loading if no cache
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(cachedEntry?.hasMore ?? true);
  const [truncated, setTruncated] = useState(cachedEntry?.truncated ?? false);
  const [beliefEnabled, setBeliefEnabled] = useState<boolean | null>(
    cachedEntry?.beliefEnabled ?? null,
  );
  // Bumped whenever a network fetch releases the fetching lock, so a
  // view/category change that arrived mid-fetch re-runs once idle.
  const [fetchIdleTick, setFetchIdleTick] = useState(0);

  // Use ref for offset to avoid dependency issues
  const offsetRef = useRef(cachedEntry?.offset || 0);
  const cursorRef = useRef<string | null>(cachedEntry?.nextCursor || null);
  const feedbackIdsRef = useRef(new Map<string, string>());
  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);
  // In-flight canonical refresh, shared with concurrent callers (see refresh).
  const refreshInFlightRef = useRef<Promise<boolean> | null>(null);
  // Track if initial fetch is done
  const initializedRef = useRef(false);
  const capabilityRef = useRef<boolean | null>(cachedEntry?.beliefEnabled ?? null);
  const capabilityRefreshRef = useRef(cachedEntry?.beliefEnabled === true);
  const fallbackRefreshRef = useRef(false);
  const scopeKeyRef = useRef<string | null>(null);
  const scopeGenerationRef = useRef(0);
  const activeStateScopeRef = useRef<string | null>(null);
  const previousScopeRef = useRef<MemoryCacheScope | null>(null);
  const currentScopeRef = useRef<MemoryCacheScope | null>(null);
  currentScopeRef.current = memoryCacheScope;
  // Latest categories+view query, assigned every render so an in-flight
  // request can detect the visible query moved on before its response lands.
  const latestQueryRef = useRef('');
  latestQueryRef.current = `${JSON.stringify(activeCategories)}:${memoryView}`;
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
    const scopedCache = cacheKey ? getFromCache(cacheKey) : null;
    capabilityRef.current = scopedCache?.beliefEnabled ?? null;
    capabilityRefreshRef.current = scopedCache?.beliefEnabled === true;
    fallbackRefreshRef.current = false;
    feedbackIdsRef.current.clear();
    offsetRef.current = 0;
    cursorRef.current = null;
    setMemories([]);
    setLoading(Boolean(scopeKey));
    setError(null);
    setHasMore(true);
    setTruncated(false);
    setBeliefEnabled(scopedCache?.beliefEnabled ?? null);

    if (previousScope) {
      deleteCachePattern(invalidationPatterns.memories, previousScope);
      void invalidateMemoryCache(previousScope);
    }
  }, [memoryCacheScope, scopeKey]);

  const applyCapability = useCallback((capability: boolean | null) => {
    const previouslyEnabled = capabilityRef.current === true;
    capabilityRef.current = capability;
    if (capability !== true) capabilityRefreshRef.current = false;
    setBeliefEnabled(capability);

    // A server that withdraws the beta header must not leave a cached beta
    // view visible or keep sending its optional query. Clear both browser
    // cache layers, return to the released surface, and let the view-change
    // effect issue a fresh unqualified request.
    if (capability !== true && previouslyEnabled) {
      fallbackRefreshRef.current = true;
      const scope = currentScopeRef.current;
      if (scope) {
        deleteCachePattern(invalidationPatterns.memories, scope);
        void invalidateMemoryCache(scope);
      }
      setMemoryView('useful_now');
      setMemories([]);
      setHasMore(true);
      setTruncated(false);
      offsetRef.current = 0;
      cursorRef.current = null;
    }
  }, []);

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
        // Discover beta capability through the response header first. Until
        // then preserve the released endpoint semantics by omitting view.
        view: capabilityRef.current === true ? memoryView : undefined,
        categories: categories.length > 0 ? categories : undefined,
      });
    },
    [limit, memoryView],
  );

  // Initial load - check cache first (memory → IndexedDB → network)
  useEffect(() => {
    if (!scopeKey || authLoading || !memoryCacheScope || !cacheKey) return;
    if (initializedRef.current) return;
    initializedRef.current = true;

    const requestScopeKey = scopeKey;
    const requestGeneration = scopeGenerationRef.current;
    const requestQuery = `${JSON.stringify(activeCategories)}:${memoryView}`;
    const isCurrentRequest = () =>
      scopeKeyRef.current === requestScopeKey &&
      scopeGenerationRef.current === requestGeneration;
    // Fence by query as well as scope: a view/category change mid-request
    // must not apply the old query's page to the newly selected one.
    const isQueryCurrent = () => latestQueryRef.current === requestQuery;

    const key = cacheKey;
    const cached = getFromCache(key);

    // If we have fresh in-memory cache, use it and skip fetch
    if (cached && !isCacheStale(key) && cached.beliefEnabled !== true) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      setTruncated(cached.truncated);
      setBeliefEnabled(cached.beliefEnabled ?? null);
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
      setBeliefEnabled(cached.beliefEnabled ?? null);
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
        const indexedDBMemories =
          memoryView === 'useful_now'
            ? await getCachedMemories(memoryView, memoryCacheScope)
            : null;
        if (!isCurrentRequest() || !isQueryCurrent()) return;
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
            null,
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
        applyCapability(page.beliefEnabled);
        // Update both caches
        setToCache(
          key,
          page.memories,
          page.memories.length,
          page.nextCursor,
          pageHasMore,
          page.truncated,
          page.beliefEnabled,
        );
        if (memoryView === 'useful_now') {
          await cacheMemories(page.memories, memoryView, memoryCacheScope);
          if (!isCurrentRequest() || !isQueryCurrent()) return;
        }
      } catch (err) {
        if (!isCurrentRequest() || !isQueryCurrent()) return;
        // Check if we have any cached data to show
        let hasAnyCachedData = !!cached;
        if (!hasAnyCachedData) {
          try {
            const indexedDbMemories =
              memoryView === 'useful_now'
                ? await getCachedMemories(memoryView, memoryCacheScope)
                : null;
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
    applyCapability,
    authLoading,
    cacheKey,
    doFetch,
    activeCategories,
    limit,
    memoryCacheScope,
    memoryView,
    scopeKey,
  ]);

  // Handle category/view changes (after initial load)
  const prevQueryRef = useRef<string>(
    `${JSON.stringify(activeCategories)}:${memoryView}`,
  );
  useEffect(() => {
    if (!scopeKey || authLoading || !memoryCacheScope) return;
    const currentQuery = `${JSON.stringify(activeCategories)}:${memoryView}`;
    if (prevQueryRef.current === currentQuery) return;

    // Only refetch if already initialized
    if (!initializedRef.current) return;

    const key = getCacheKey(activeCategories, memoryView, memoryCacheScope);
    if (!key) return;
    const cached = getFromCache(key);

    // If we have cache for this category, use it immediately
    if (cached) {
      setMemories(cached.memories);
      setHasMore(cached.hasMore);
      setTruncated(cached.truncated);
      setBeliefEnabled(cached.beliefEnabled ?? null);
      offsetRef.current = cached.offset;
      cursorRef.current = cached.nextCursor;

      // If not stale, we're done
      if (!isCacheStale(key)) {
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
        applyCapability(page.beliefEnabled);
        // Update cache
        setToCache(
          key,
          page.memories,
          page.memories.length,
          page.nextCursor,
          pageHasMore,
          page.truncated,
          page.beliefEnabled,
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
    applyCapability,
    authLoading,
    doFetch,
    fetchIdleTick,
    limit,
    memoryCacheScope,
    memoryView,
    scopeKey,
  ]);

  // Load more (pagination)
  const loadMore = useCallback(async () => {
    const scope = currentScopeRef.current;
    const requestedScopeKey = scopeKeyRef.current;
    if (!scope || !requestedScopeKey || fetchingRef.current || !hasMore) return;
    fetchingRef.current = true;
    setLoading(true);

    const key = getCacheKey(activeCategories, memoryView, scope);
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
        setToCache(
          key,
          updated,
          newOffset,
          page.nextCursor,
          pageHasMore,
          page.truncated,
          page.beliefEnabled,
        );
        return updated;
      });

      offsetRef.current += page.memories.length;
      cursorRef.current = page.nextCursor;
      setHasMore(pageHasMore);
      setTruncated(page.truncated);
      applyCapability(page.beliefEnabled);
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
  }, [activeCategories, applyCapability, doFetch, hasMore, limit, memoryView]);

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

      const key = getCacheKey(activeCategories, memoryView, scope);
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
          applyCapability(page.beliefEnabled);
          // Update cache
          setToCache(
            key,
            page.memories,
            page.memories.length,
            page.nextCursor,
            pageHasMore,
            page.truncated,
            page.beliefEnabled,
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
    [activeCategories, applyCapability, doFetch, limit, memoryView],
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

  // The discovery request intentionally omits the beta-only view query. Once
  // the server advertises the capability, re-read the default Useful now
  // surface with the explicit view so first load is server-selected.
  useEffect(() => {
    if (beliefEnabled !== true || capabilityRefreshRef.current) return;
    if (fetchingRef.current) return;
    capabilityRefreshRef.current = true;
    void refresh();
  }, [beliefEnabled, loading, refresh]);

  useEffect(() => {
    if (beliefEnabled === true || !fallbackRefreshRef.current) return;
    if (fetchingRef.current) return;
    fallbackRefreshRef.current = false;
    void refresh();
  }, [beliefEnabled, loading, refresh]);

  const setMemoryUse = useCallback(
    async (id: string, action: MemoryUseAction): Promise<boolean> => {
      if (!scopeKeyRef.current || !currentScopeRef.current) return false;
      const isCurrentRequest = captureScopeGeneration();
      const key = `${id}:${action}`;
      let feedbackId = feedbackIdsRef.current.get(key);
      if (!feedbackId) {
        feedbackId = createFeedbackId();
        feedbackIdsRef.current.set(key, feedbackId);
      }

      try {
        await setMemoryUseRequest(id, action, feedbackId);
        if (!isCurrentRequest()) return false;
        // Re-read the canonical row before changing the visible list. A suppress
        // action must remain inspectable in history and must never be simulated
        // by deleting the row from this client cache.
        const refreshed = await refresh(true);
        if (!isCurrentRequest() || !refreshed) return false;
        feedbackIdsRef.current.delete(key);
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update memory use');
        return false;
      }
    },
    [refresh],
  );

  // Add memory
  const addMemory = useCallback(
    async (
      content: string,
      visibility: MemoryVisibility = 'public',
    ): Promise<Memory | null> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Edit memory
  const editMemory = useCallback(
    async (id: string, content: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Remove memory
  const removeMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
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
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Toggle visibility
  const toggleVisibility = useCallback(
    async (id: string, visibility: MemoryVisibility): Promise<boolean> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Accept memory
  const acceptMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Reject memory
  const rejectMemory = useCallback(
    async (id: string): Promise<boolean> => {
      const key = getCacheKey(activeCategories, memoryView, currentScopeRef.current);
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
    [activeCategories, memoryView],
  );

  // Set categories
  const setCategories = useCallback((categories: MemoryCategory[]) => {
    setActiveCategories(categories);
    offsetRef.current = 0;
    cursorRef.current = null;
  }, []);

  const setMemoryViewAndReset = useCallback((view: MemoryView) => {
    setMemoryView(view);
    offsetRef.current = 0;
    cursorRef.current = null;
    setTruncated(false);
  }, []);

  const scopeIsActive =
    Boolean(scopeKey) && !authLoading && activeStateScopeRef.current === scopeKey;

  return {
    memories: scopeIsActive ? memories : [],
    loading: scopeIsActive ? loading : Boolean(scopeKey),
    error: scopeIsActive ? error : null,
    hasMore: scopeIsActive ? hasMore : true,
    truncated: scopeIsActive ? truncated : false,
    beliefEnabled: scopeIsActive ? beliefEnabled : null,
    memoryView,
    setMemoryView: setMemoryViewAndReset,
    setMemoryUse,
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
