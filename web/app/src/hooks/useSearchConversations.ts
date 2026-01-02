'use client';

import { useState, useCallback, useRef } from 'react';
import { searchConversations as searchConversationsApi } from '@/lib/api';
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

export function useSearchConversations(): UseSearchConversationsReturn {
  const [results, setResults] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const currentQueryRef = useRef<string>('');

  const search = useCallback(async (query: string) => {
    // Don't search if query is empty
    if (!query.trim()) {
      setResults([]);
      setCurrentPage(1);
      setTotalPages(0);
      currentQueryRef.current = '';
      return;
    }

    currentQueryRef.current = query;
    setLoading(true);
    setError(null);

    try {
      const response = await searchConversationsApi({
        query,
        page: 1,
        perPage: 20,
      });

      setResults(response.items);
      setCurrentPage(response.current_page);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      console.error('Search error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    if (loading || currentPage >= totalPages || !currentQueryRef.current) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await searchConversationsApi({
        query: currentQueryRef.current,
        page: currentPage + 1,
        perPage: 20,
      });

      setResults((prev) => [...prev, ...response.items]);
      setCurrentPage(response.current_page);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more results');
      console.error('Load more error:', err);
    } finally {
      setLoading(false);
    }
  }, [loading, currentPage, totalPages]);

  const clear = useCallback(() => {
    setResults([]);
    setCurrentPage(1);
    setTotalPages(0);
    setError(null);
    currentQueryRef.current = '';
  }, []);

  return {
    results,
    loading,
    error,
    currentPage,
    totalPages,
    search,
    loadMore,
    clear,
  };
}
