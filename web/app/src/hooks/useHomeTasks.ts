'use client';

import { useCallback, useMemo, useState } from 'react';
import { getActionItems, toggleActionItemCompleted } from '@/lib/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import type { ActionItem } from '@/types/conversation';

/**
 * The open action items the hub puts in front of you.
 *
 * Deliberately not `useActionItems`: that one pulls 500 items to drive the
 * Tasks page's grouping, calendar and stats, none of which the hub renders. The
 * hub shows a handful of rows, so it asks for a handful.
 */
const LIMIT = 20;

export interface UseHomeTasksReturn {
  items: ActionItem[];
  loading: boolean;
  error: string | null;
  complete: (id: string) => Promise<void>;
}

export function useHomeTasks(): UseHomeTasksReturn {
  // Listed without `completed: false`: that is a server-side equality filter,
  // and legacy documents whose `completed` field is missing or null are excluded
  // by it even though every other surface treats them as open. The unfiltered
  // list is active-first and includes those documents; openness is decided here
  // the same way the Tasks page decides it.
  const { data, loading, error } = useAsyncResource('home:tasks', () =>
    getActionItems({ limit: LIMIT }),
  );

  // Completed ids are held here rather than refetching: the row should leave
  // the list the moment it is ticked, and the hub has no other view of it.
  const [completedIds, setCompletedIds] = useState<string[]>([]);

  const items = useMemo(
    () =>
      (data?.items ?? []).filter(
        (item) => !item.completed && !completedIds.includes(item.id),
      ),
    [data, completedIds],
  );

  const complete = useCallback(async (id: string) => {
    setCompletedIds((prev) => [...prev, id]);
    try {
      await toggleActionItemCompleted(id, true);
    } catch (err) {
      console.error('Failed to complete task:', err);
      setCompletedIds((prev) => prev.filter((completed) => completed !== id));
    }
  }, []);

  return { items, loading, error, complete };
}
