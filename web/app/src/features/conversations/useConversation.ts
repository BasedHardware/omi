'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import { getConversation } from '@/features/conversations/api';
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

export function createConversationStore() {
  const conversation = createSignal<Conversation | null>(null);
  const loading = createSignal(true);
  const error = createSignal<string | null>(null);

  const load = async (id: string | null, enabled: boolean) => {
    if (!enabled || !id) {
      conversation.set(null);
      loading.set(false);
      return;
    }

    loading.set(true);
    error.set(null);
    try {
      conversation.set(await getConversation(id));
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Failed to load conversation');
      console.error('Failed to fetch conversation:', err);
    } finally {
      loading.set(false);
    }
  };

  const update = (updated: Conversation) => {
    conversation.set(updated);
  };

  return { conversation, loading, error, load, update };
}

export function useConversation(
  id: string | null,
  options: UseConversationOptions = {},
): UseConversationReturn {
  const { enabled = true } = options;
  const store = useMemo(() => createConversationStore(), [id, enabled]);

  useEffect(() => {
    void store.load(id, enabled);
  }, [store, id, enabled]);

  return {
    conversation: useSignalValue(store.conversation),
    loading: useSignalValue(store.loading),
    error: useSignalValue(store.error),
    refresh: useCallback(() => store.load(id, enabled), [store, id, enabled]),
    update: useCallback((updated: Conversation) => store.update(updated), [store]),
  };
}
