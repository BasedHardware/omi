'use client';

import { useCallback, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import { searchConversations as searchConversationsApi } from '@/features/conversations/api';
import type { Conversation } from '@/types/conversation';

interface UseSearchConversationsReturn {
  results: Conversation[];
  loading: boolean;
  error: string | null;
  currentPage: number;
  totalPages: number;
  search: (query: string) => Promise<void>;
  loadMore: () => Promise<void>;
  clear: () => void;
}

export function createSearchConversationsStore() {
  const results = createSignal<Conversation[]>([]);
  const loading = createSignal(false);
  const error = createSignal<string | null>(null);
  const currentPage = createSignal(1);
  const totalPages = createSignal(0);
  let currentQuery = '';

  const reset = () => {
    results.set([]);
    currentPage.set(1);
    totalPages.set(0);
    currentQuery = '';
  };

  const search = async (query: string) => {
    if (!query.trim()) {
      error.set(null);
      reset();
      return;
    }

    currentQuery = query;
    loading.set(true);
    error.set(null);

    try {
      const response = await searchConversationsApi({
        query,
        page: 1,
        perPage: 20,
      });
      results.set(response.items);
      currentPage.set(response.current_page);
      totalPages.set(response.total_pages);
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Search failed');
      console.error('Search error:', err);
    } finally {
      loading.set(false);
    }
  };

  const loadMore = async () => {
    if (loading.peek() || currentPage.peek() >= totalPages.peek() || !currentQuery) {
      return;
    }

    loading.set(true);
    error.set(null);

    try {
      const response = await searchConversationsApi({
        query: currentQuery,
        page: currentPage.peek() + 1,
        perPage: 20,
      });
      results.set((prev) => [...prev, ...response.items]);
      currentPage.set(response.current_page);
      totalPages.set(response.total_pages);
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Failed to load more results');
      console.error('Load more error:', err);
    } finally {
      loading.set(false);
    }
  };

  const clear = () => {
    error.set(null);
    reset();
  };

  return { results, loading, error, currentPage, totalPages, search, loadMore, clear };
}

export function useSearchConversations(): UseSearchConversationsReturn {
  const store = useMemo(() => createSearchConversationsStore(), []);

  return {
    results: useSignalValue(store.results),
    loading: useSignalValue(store.loading),
    error: useSignalValue(store.error),
    currentPage: useSignalValue(store.currentPage),
    totalPages: useSignalValue(store.totalPages),
    search: useCallback((query: string) => store.search(query), [store]),
    loadMore: useCallback(() => store.loadMore(), [store]),
    clear: useCallback(() => store.clear(), [store]),
  };
}
