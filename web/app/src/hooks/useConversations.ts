'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { getConversations, GetConversationsParams } from '@/lib/api';
import type { Conversation, GroupedConversations } from '@/types/conversation';
import { formatRelativeDate } from '@/lib/utils';
import {
  getCache,
  setCache,
  onCacheInvalidation,
  invalidationPatterns,
  CACHE_TTL,
  cacheKeys,
} from '@/lib/cache';

// Cache entry structure
interface CacheEntry {
  conversations: Conversation[];
  offset: number;
  hasMore: boolean;
}

function getCacheKey(folderId?: string, startDate?: Date, endDate?: Date): string {
  return cacheKeys.conversations(
    folderId,
    startDate?.toISOString().split('T')[0],
    endDate?.toISOString().split('T')[0]
  );
}

function getFromCache(key: string): CacheEntry | null {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.data : null;
}

function isCacheStale(key: string): boolean {
  const cached = getCache<CacheEntry>(key);
  return cached ? cached.isStale : true;
}

function setToCache(key: string, conversations: Conversation[], offset: number, hasMore: boolean): void {
  setCache<CacheEntry>(key, { conversations, offset, hasMore }, CACHE_TTL.MEDIUM);
}

interface UseConversationsOptions extends GetConversationsParams {
  enabled?: boolean;
}

interface UseConversationsReturn {
  conversations: Conversation[];
  groupedConversations: GroupedConversations;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
}

/**
 * Hook to fetch and manage conversations
 */
export function useConversations(
  options: UseConversationsOptions = {}
): UseConversationsReturn {
  const { enabled = true, limit = 50, ...params } = options;

  // Get cache key and check for cached data
  const cacheKey = getCacheKey(params.folderId, params.startDate, params.endDate);
  const cachedEntry = getFromCache(cacheKey);

  const [conversations, setConversations] = useState<Conversation[]>(cachedEntry?.conversations || []);
  const [loading, setLoading] = useState(!cachedEntry); // Only show loading if no cache
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(cachedEntry?.offset || 0);
  const [hasMore, setHasMore] = useState(cachedEntry?.hasMore ?? true);
  const [hasProcessing, setHasProcessing] = useState(false);

  // Track previous params to detect changes
  const prevStartDate = useRef(params.startDate?.getTime());
  const prevEndDate = useRef(params.endDate?.getTime());
  const prevFolderId = useRef(params.folderId);

  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);

  // Group conversations by date - memoized for performance
  const groupedConversations = useMemo<GroupedConversations>(() => {
    return conversations.reduce(
      (groups, conversation) => {
        const date = new Date(conversation.started_at || conversation.created_at);
        const dateKey = formatRelativeDate(date);

        if (!groups[dateKey]) {
          groups[dateKey] = [];
        }
        groups[dateKey].push(conversation);

        return groups;
      },
      {} as GroupedConversations
    );
  }, [conversations]);

  // Fetch conversations
  const fetchConversations = useCallback(
    async (currentOffset: number, append: boolean = false, backgroundRefresh: boolean = false) => {
      if (!enabled) return;

      // Prevent concurrent fetches
      if (fetchingRef.current) return;
      fetchingRef.current = true;

      const key = getCacheKey(params.folderId, params.startDate, params.endDate);

      try {
        // Only show loading spinner if not a background refresh and no cached data
        if (!backgroundRefresh) {
          setLoading(true);
        }
        setError(null);

        const data = await getConversations({
          limit,
          offset: currentOffset,
          statuses: params.statuses,
          includeDiscarded: params.includeDiscarded,
          startDate: params.startDate,
          endDate: params.endDate,
          folderId: params.folderId,
        });

        // Sort by date descending
        const sorted = data.sort((a, b) => {
          const dateA = new Date(a.started_at || a.created_at);
          const dateB = new Date(b.started_at || b.created_at);
          return dateB.getTime() - dateA.getTime();
        });

        // Use functional update to avoid conversations in dependency array
        const hasMoreData = data.length === limit;
        setHasMore(hasMoreData);

        setConversations(prev => {
          const newConversations = append ? [...prev, ...sorted] : sorted;
          // Save to cache
          setToCache(key, newConversations, currentOffset, hasMoreData);
          return newConversations;
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversations');
        console.error('Failed to fetch conversations:', err);
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    },
    // Only depend on primitive values, not objects
    [enabled, limit, params.statuses, params.includeDiscarded, params.startDate, params.endDate, params.folderId]
  );

  // Initial fetch and refetch when filter params change
  useEffect(() => {
    const startDateChanged = params.startDate?.getTime() !== prevStartDate.current;
    const endDateChanged = params.endDate?.getTime() !== prevEndDate.current;
    const folderIdChanged = params.folderId !== prevFolderId.current;

    // Update refs
    prevStartDate.current = params.startDate?.getTime();
    prevEndDate.current = params.endDate?.getTime();
    prevFolderId.current = params.folderId;

    const key = getCacheKey(params.folderId, params.startDate, params.endDate);
    const cached = getFromCache(key);

    // If filter params changed, check cache for new filter
    if (startDateChanged || endDateChanged || folderIdChanged) {
      if (cached) {
        // Load from cache immediately
        setConversations(cached.conversations);
        setOffset(cached.offset);
        setHasMore(cached.hasMore);
        setLoading(false);

        // If cache is stale, do background refresh
        if (isCacheStale(key)) {
          fetchConversations(0, false, true);
        }
      } else {
        // No cache, do normal fetch
        setOffset(0);
        setHasMore(true);
        fetchConversations(0, false);
      }
    } else if (conversations.length === 0 && !cached) {
      // Initial load with no cache
      setOffset(0);
      setHasMore(true);
      fetchConversations(0, false);
    } else if (cached && isCacheStale(key)) {
      // Have cached data but it's stale, do background refresh
      fetchConversations(0, false, true);
    }
  }, [params.startDate, params.endDate, params.folderId, fetchConversations]);

  // Subscribe to cache invalidation - refetch when conversations are modified
  useEffect(() => {
    const unsubscribe = onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.conversations) {
        // Cache was invalidated, do a fresh fetch
        fetchConversations(0, false, false);
      }
    });
    return unsubscribe;
  }, [fetchConversations]);

  // Track if any conversations are processing
  useEffect(() => {
    const processing = conversations.some(c => c.status === 'processing');
    setHasProcessing(processing);
  }, [conversations]);

  // Poll for updates while conversations are processing
  useEffect(() => {
    if (!hasProcessing) return;

    const pollInterval = setInterval(() => {
      fetchConversations(0, false, true); // Background refresh, skip cache
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(pollInterval);
  }, [hasProcessing, fetchConversations]);

  // Load more conversations
  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;

    const newOffset = offset + limit;
    setOffset(newOffset);
    await fetchConversations(newOffset, true);
  }, [loading, hasMore, offset, limit, fetchConversations]);

  // Refresh conversations (reset and reload)
  const refresh = useCallback(async () => {
    setOffset(0);
    setHasMore(true);
    await fetchConversations(0, false);
  }, [fetchConversations]);

  return {
    conversations,
    groupedConversations,
    loading,
    error,
    hasMore,
    loadMore,
    refresh,
  };
}
