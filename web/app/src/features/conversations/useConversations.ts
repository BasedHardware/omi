'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import { getConversations, type GetConversationsParams } from '@/features/conversations/api';
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

interface CacheEntry {
  conversations: Conversation[];
  offset: number;
  hasMore: boolean;
}

function getCacheKey(folderId?: string, startDate?: Date, endDate?: Date): string {
  return cacheKeys.conversations(
    folderId,
    startDate?.toISOString().split('T')[0],
    endDate?.toISOString().split('T')[0],
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

function setToCache(
  key: string,
  conversations: Conversation[],
  offset: number,
  hasMore: boolean,
): void {
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

function sortByDateDesc(data: Conversation[]): Conversation[] {
  return [...data].sort((a, b) => {
    const dateA = new Date(a.started_at || a.created_at);
    const dateB = new Date(b.started_at || b.created_at);
    return dateB.getTime() - dateA.getTime();
  });
}

export function createConversationsStore(options: {
  enabled: boolean;
  limit: number;
  params: GetConversationsParams;
}) {
  const { enabled, limit, params } = options;
  const cacheKey = getCacheKey(params.folderId, params.startDate, params.endDate);
  const cached = getFromCache(cacheKey);

  const conversations = createSignal<Conversation[]>(cached?.conversations ?? []);
  const loading = createSignal(!cached);
  const error = createSignal<string | null>(null);
  const hasMore = createSignal(cached?.hasMore ?? true);
  let offset = cached?.offset ?? 0;
  let fetching = false;

  const fetchPage = async (
    currentOffset: number,
    append: boolean,
    backgroundRefresh: boolean,
  ) => {
    if (!enabled || fetching) return;
    fetching = true;

    try {
      if (!backgroundRefresh) {
        loading.set(true);
      }
      error.set(null);

      const data = await getConversations({
        limit,
        offset: currentOffset,
        statuses: params.statuses,
        includeDiscarded: params.includeDiscarded,
        startDate: params.startDate,
        endDate: params.endDate,
        folderId: params.folderId,
      });

      const sorted = sortByDateDesc(data);
      const hasMoreData = data.length === limit;
      hasMore.set(hasMoreData);

      const next = append ? [...conversations.peek(), ...sorted] : sorted;
      conversations.set(next);
      setToCache(cacheKey, next, currentOffset, hasMoreData);
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Failed to load conversations');
      console.error('Failed to fetch conversations:', err);
    } finally {
      loading.set(false);
      fetching = false;
    }
  };

  const ensureLoaded = () => {
    if (!enabled) return;
    const cachedNow = getFromCache(cacheKey);
    if (cachedNow && !isCacheStale(cacheKey)) return;
    if (cachedNow && isCacheStale(cacheKey)) {
      void fetchPage(0, false, true);
      return;
    }
    offset = 0;
    hasMore.set(true);
    void fetchPage(0, false, false);
  };

  const loadMore = async () => {
    if (loading.peek() || !hasMore.peek()) return;
    offset += limit;
    await fetchPage(offset, true, false);
  };

  const refresh = async () => {
    offset = 0;
    hasMore.set(true);
    await fetchPage(0, false, false);
  };

  const reloadAfterInvalidation = () => {
    void fetchPage(0, false, false);
  };

  const refreshInBackground = () => {
    void fetchPage(0, false, true);
  };

  return {
    conversations,
    loading,
    error,
    hasMore,
    ensureLoaded,
    loadMore,
    refresh,
    reloadAfterInvalidation,
    refreshInBackground,
  };
}

export function useConversations(
  options: UseConversationsOptions = {},
): UseConversationsReturn {
  const { enabled = true, limit = 50, ...params } = options;
  const statusesKey = JSON.stringify(params.statuses ?? null);
  const startMs = params.startDate?.getTime();
  const endMs = params.endDate?.getTime();

  const store = useMemo(
    () =>
      createConversationsStore({
        enabled,
        limit,
        params: {
          statuses: params.statuses,
          includeDiscarded: params.includeDiscarded,
          startDate: params.startDate,
          endDate: params.endDate,
          folderId: params.folderId,
        },
      }),
    // Primitive filter identity: a new Date each render must not recreate the store.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, limit, statusesKey, params.includeDiscarded, startMs, endMs, params.folderId],
  );

  useEffect(() => {
    store.ensureLoaded();
  }, [store]);

  useEffect(() => {
    return onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.conversations) {
        store.reloadAfterInvalidation();
      }
    });
  }, [store]);

  const conversations = useSignalValue(store.conversations);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);
  const hasMore = useSignalValue(store.hasMore);

  const hasProcessing = conversations.some((c) => c.status === 'processing');

  useEffect(() => {
    if (!hasProcessing) return;

    let pollCount = 0;
    let timeoutId: ReturnType<typeof setTimeout>;

    const poll = () => {
      store.refreshInBackground();
      pollCount++;
      const nextInterval = Math.min(5000 * Math.pow(2, Math.floor(pollCount / 3)), 30000);
      timeoutId = setTimeout(poll, nextInterval);
    };

    timeoutId = setTimeout(poll, 5000);
    return () => clearTimeout(timeoutId);
  }, [hasProcessing, store]);

  const groupedConversations = useMemo<GroupedConversations>(() => {
    return conversations.reduce((groups, conversation) => {
      const date = new Date(conversation.started_at || conversation.created_at);
      const dateKey = formatRelativeDate(date);
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(conversation);
      return groups;
    }, {} as GroupedConversations);
  }, [conversations]);

  const loadMore = useCallback(() => store.loadMore(), [store]);
  const refresh = useCallback(() => store.refresh(), [store]);

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
