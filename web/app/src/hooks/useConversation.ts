'use client';

import { useState, useEffect, useCallback } from 'react';
import { getConversation } from '@/lib/api';
import type { Conversation } from '@/types/conversation';

interface UseConversationOptions {
  enabled?: boolean;
}

interface UseConversationReturn {
  conversation: Conversation | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  update: (conversation: Conversation) => void;
}

/**
 * Hook to fetch a single conversation by ID
 */
export function useConversation(
  id: string | null,
  options: UseConversationOptions = {}
): UseConversationReturn {
  const { enabled = true } = options;

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConversation = useCallback(async () => {
    if (!enabled || !id) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const data = await getConversation(id);
      setConversation(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation');
      console.error('Failed to fetch conversation:', err);
    } finally {
      setLoading(false);
    }
  }, [enabled, id]);

  useEffect(() => {
    fetchConversation();
  }, [fetchConversation]);

  const refresh = useCallback(async () => {
    await fetchConversation();
  }, [fetchConversation]);

  const update = useCallback((updatedConversation: Conversation) => {
    setConversation(updatedConversation);
  }, []);

  return {
    conversation,
    loading,
    error,
    refresh,
    update,
  };
}
