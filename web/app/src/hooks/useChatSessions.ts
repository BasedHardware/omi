'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignal } from '@tschk/moonshine-react';
import {
  createChatSession,
  deleteChatSession,
  getChatSessions,
  updateChatSession,
} from '@/lib/api';
import type { ChatSession } from '@/types/chatSessions';

export interface UseChatSessionsReturn {
  sessions: ChatSession[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addSession: (title?: string) => Promise<ChatSession | null>;
  renameSession: (id: string, title: string) => Promise<void>;
  toggleStar: (id: string) => Promise<void>;
  /** Re-throws on failure so callers can avoid re-threading to a live session. */
  removeSession: (id: string) => Promise<void>;
}

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/**
 * The user's chat sessions and their mutations, in moonshine signals so
 * optimistic writes can read the committed list synchronously on rollback —
 * the same shape as `createGoalsStore`.
 */
export function createChatSessionsStore() {
  const sessions = createSignal<ChatSession[]>([]);
  const loading = createSignal(true);
  const error = createSignal<string | null>(null);

  const load = async () => {
    loading.set(true);
    try {
      sessions.set(await getChatSessions());
      error.set(null);
    } catch (err) {
      console.error('Failed to load chat sessions:', err);
      error.set(messageFor(err, 'Failed to load chats'));
    } finally {
      loading.set(false);
    }
  };

  const optimistic = async (
    id: string,
    apply: (session: ChatSession) => ChatSession,
    request: () => Promise<ChatSession>,
    failureMessage: string,
  ) => {
    const previous = sessions.peek().find((session) => session.id === id);
    sessions.set((current) =>
      current.map((session) => (session.id === id ? apply(session) : session)),
    );

    try {
      const updated = await request();
      sessions.set((current) =>
        current.map((session) => (session.id === id ? updated : session)),
      );
      error.set(null);
    } catch (err) {
      console.error(failureMessage, err);
      if (previous) {
        sessions.set((current) =>
          current.map((session) => (session.id === id ? previous : session)),
        );
      }
      error.set(messageFor(err, failureMessage));
    }
  };

  const add = async (title?: string): Promise<ChatSession | null> => {
    try {
      const created = await createChatSession(title ? { title } : {});
      sessions.set((current) => [created, ...current]);
      error.set(null);
      return created;
    } catch (err) {
      console.error('Failed to create chat:', err);
      error.set(messageFor(err, 'Failed to create chat'));
      return null;
    }
  };

  /**
   * Deletes and re-throws on failure. `deleteAndRethread` relies on that: a
   * failed delete must not move the reader off a session that still exists.
   */
  const remove = async (id: string) => {
    const removed = sessions.peek().find((session) => session.id === id);
    sessions.set((current) => current.filter((session) => session.id !== id));

    try {
      await deleteChatSession(id);
      error.set(null);
    } catch (err) {
      console.error('Failed to delete chat:', err);
      if (removed) {
        sessions.set((current) => [removed, ...current]);
      }
      error.set(messageFor(err, 'Failed to delete chat'));
      throw err;
    }
  };

  return { sessions, loading, error, load, optimistic, add, remove };
}

export function useChatSessions(): UseChatSessionsReturn {
  const store = useMemo(() => createChatSessionsStore(), []);

  // Loaded here rather than from the factory: useMemo may run more than once
  // per commit (StrictMode renders twice), and loading in the factory would
  // fetch once per discarded store. This writes signals, not React state.
  useEffect(() => {
    void store.load();
  }, [store]);

  const sessions = useSignal(store.sessions);
  const loading = useSignal(store.loading);
  const error = useSignal(store.error);

  const renameSession = useCallback(
    (id: string, title: string) => {
      const next = title.trim();
      const current = store.sessions.peek().find((session) => session.id === id);
      // The desktop row calls this on every blur; a no-op rename must not write.
      if (!next || !current || next === (current.title ?? '')) {
        return Promise.resolve();
      }
      return store.optimistic(
        id,
        (session) => ({ ...session, title: next }),
        () => updateChatSession(id, { title: next }),
        'Failed to rename chat',
      );
    },
    [store],
  );

  const toggleStar = useCallback(
    (id: string) => {
      const current = store.sessions.peek().find((session) => session.id === id);
      if (!current) return Promise.resolve();
      const starred = !current.starred;
      return store.optimistic(
        id,
        (session) => ({ ...session, starred }),
        () => updateChatSession(id, { starred }),
        'Failed to star chat',
      );
    },
    [store],
  );

  return {
    sessions,
    loading,
    error,
    refresh: store.load,
    addSession: store.add,
    renameSession,
    toggleStar,
    removeSession: store.remove,
  };
}
