'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getConversations, GetConversationsParams } from '@/lib/api';
import type { Conversation, GroupedConversations } from '@/types/conversation';
import { formatRelativeDate } from '@/lib/utils';

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

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Track previous params to detect changes
  const prevStartDate = useRef(params.startDate?.getTime());
  const prevEndDate = useRef(params.endDate?.getTime());
  const prevFolderId = useRef(params.folderId);

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
    async (currentOffset: number, append: boolean = false) => {
      if (!enabled) return;

      try {
        setLoading(true);
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

        if (append) {
          setConversations((prev) => [...prev, ...sorted]);
        } else {
          setConversations(sorted);
        }

        // Check if there are more to load
        setHasMore(data.length === limit);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversations');
        console.error('Failed to fetch conversations:', err);
      } finally {
        setLoading(false);
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

    // Fetch if filter params changed or this is initial load
    if (startDateChanged || endDateChanged || folderIdChanged || conversations.length === 0) {
      setOffset(0);
      setHasMore(true);
      fetchConversations(0, false);
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
