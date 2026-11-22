// Preserve links for failures hidden from any loaded Home list or search.
// This account-scoped memory does not fetch history or persist a projection.
import { useCallback, useEffect, useRef, useState } from 'react';
import { isFailedConversation } from '@/lib/conversationHome';
import type { Conversation } from '@/types/conversation';

export function useActivityFailures(
  home: Conversation[],
  search: Conversation[],
  owner?: string,
) {
  const identity = useRef(owner);
  const removed = useRef(new Set<string>());
  const settled = useRef(new Map<string, Set<Conversation>>());
  const blocked = useRef<{ home: Conversation[]; search: Conversation[] } | null>(null);
  const [known, setKnown] = useState<Conversation[]>([]);
  useEffect(() => {
    if (identity.current !== owner) {
      identity.current = owner;
      blocked.current = { home, search };
      removed.current.clear();
      settled.current.clear();
      setKnown([]);
      return;
    }
    const incoming = [
      ...(blocked.current?.home === home ? [] : home),
      ...(blocked.current?.search === search ? [] : search),
    ];
    setKnown((previous) => {
      const byId = new Map(previous.map((row) => [row.id, row]));
      for (const row of incoming) {
        // A retry can resolve an off-page row while the old loaded arrays remain.
        // Ignore those snapshots, but allow a fresh failure from a later read.
        if (settled.current.get(row.id)?.has(row)) continue;
        if (isFailedConversation(row) && !row.discarded && !removed.current.has(row.id))
          byId.set(row.id, row);
        else byId.delete(row.id);
      }
      const next = [...byId.values()];
      return next.length === previous.length &&
        next.every((row, i) => row === previous[i])
        ? previous
        : next;
    });
  }, [home, search, owner]);
  const forget = useCallback((ids: string[]) => {
    ids.forEach((id) => removed.current.add(id));
    setKnown((rows) => rows.filter((row) => !removed.current.has(row.id)));
  }, []);
  const resolveRetry = useCallback(
    (id: string) => {
      if (identity.current !== owner) return;
      settled.current.set(
        id,
        new Set([...known, ...home, ...search].filter((row) => row.id === id)),
      );
      setKnown((rows) => rows.filter((row) => row.id !== id));
    },
    [known, home, search, owner],
  );
  return { failures: identity.current === owner ? known : [], forget, resolveRetry };
}
