'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getConversations, GetConversationsParams } from '@/lib/api';
import type { Conversation, GroupedConversations } from '@/types/conversation';
import { formatRelativeDate } from '@/lib/utils';

// Module-level cache that persists across component mounts
interface CacheEntry {
  conversations: Conversation[];
  offset: number;
  hasMore: boolean;
  timestamp: number;
}

const conversationCache = new Map<string, CacheEntry>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function getCacheKey(folderId?: string, startDate?: Date, endDate?: Date): string {
  const parts = [
    folderId || 'all',
    startDate?.toISOString().split('T')[0] || '',
    endDate?.toISOString().split('T')[0] || '',
  ];
  return parts.join('|');
}

function getFromCache(key: string): CacheEntry | null {
  return conversationCache.get(key) || null;
}

function setToCache(key: string, conversations: Conversation[], offset: number, hasMore: boolean): void {
  conversationCache.set(key, { conversations, offset, hasMore, timestamp: Date.now() });
}

function isCacheStale(entry: CacheEntry): boolean {
  return Date.now() - entry.timestamp > CACHE_TTL;
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

  // Track previous params to detect changes
  const prevStartDate = useRef(params.startDate?.getTime());
  const prevEndDate = useRef(params.endDate?.getTime());
  const prevFolderId = useRef(params.folderId);

  // Track if a fetch is in progress to prevent concurrent fetches
  const fetchingRef = useRef(false);

  // Group conversations by date
  const groupedConversations: GroupedConversations = conversations.reduce(
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

        const newConversations = append
          ? [...conversations, ...sorted]
          : sorted;

        setConversations(newConversations);

        // Check if there are more to load
        const hasMoreData = data.length === limit;
        setHasMore(hasMoreData);

        // Save to cache
        setToCache(key, newConversations, currentOffset, hasMoreData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversations');
        console.error('Failed to fetch conversations:', err);
      } finally {
        setLoading(false);
        fetchingRef.current = false;
      }
    },
    // Only depend on primitive values, not objects
    [enabled, limit, params.statuses, params.includeDiscarded, params.startDate, params.endDate, params.folderId, conversations]
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
        if (isCacheStale(cached)) {
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
    } else if (cached && isCacheStale(cached)) {
      // Have cached data but it's stale, do background refresh
      fetchConversations(0, false, true);
    }
  }, [params.startDate, params.endDate, params.folderId, fetchConversations]);

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
