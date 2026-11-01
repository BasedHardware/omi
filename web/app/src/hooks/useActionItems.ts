'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  getActionItems,
  createActionItem,
  toggleActionItemCompleted,
  updateActionItemDueDate,
  updateActionItemDescription,
  deleteActionItem,
  type CreateActionItemParams,
} from '@/lib/api';
import { groupActionItems } from '@/lib/actionItemGroups';
import { prependOrReplaceById } from '@/lib/actionItemList';
import { onCacheInvalidation, invalidationPatterns } from '@/lib/cache';
import { daysUntilDue } from '@/lib/taskDue';
import type { ActionItem, GroupedActionItems } from '@/types/conversation';

/**
 * Calculate task counts for a specific date
 */
function getTaskCountsForDate(
  items: ActionItem[],
  date: Date,
): { pending: number; completed: number } {
  if (!Array.isArray(items)) {
    return { pending: 0, completed: 0 };
  }

  const dateStr = date.toDateString();
  let pending = 0;
  let completed = 0;

  for (const item of items) {
    if (!item.due_at) continue;
    const itemDate = new Date(item.due_at).toDateString();
    if (itemDate === dateStr) {
      if (item.completed) {
        completed++;
      } else {
        pending++;
      }
    }
  }

  return { pending, completed };
}

export interface UseActionItemsReturn {
  items: ActionItem[];
  groupedItems: GroupedActionItems;
  loading: boolean;
  error: string | null;

  // Flat sorted list for list view (pending sorted by due date, no-date items last)
  sortedFlatList: {
    pending: ActionItem[];
    completed: ActionItem[];
  };

  // Stats
  stats: {
    total: number;
    completed: number;
    pending: number;
    overdue: number;
    noDueDateCount: number;
    todayTotal: number;
    todayCompleted: number;
    // Weekly stats
    weekCompleted: number;
    weekPending: number;
    streak: number;
  };

  // Week data for calendar strip
  weekData: Array<{
    date: Date;
    dayName: string;
    dayNumber: number;
    isToday: boolean;
    pending: number;
    completed: number;
  }>;

  // Actions
  refresh: () => Promise<void>;
  addItem: (params: CreateActionItemParams) => Promise<ActionItem | null>;
  toggleComplete: (id: string, completed: boolean) => Promise<void>;
  snooze: (id: string, days: number) => Promise<void>;
  setDueDate: (id: string, date: Date | null) => Promise<void>;
  updateDescription: (id: string, description: string) => Promise<void>;
  removeItem: (id: string) => Promise<void>;
  bulkComplete: (ids: string[]) => Promise<void>;
  bulkDelete: (ids: string[]) => Promise<void>;
  bulkSnooze: (ids: string[], days: number) => Promise<void>;
  bulkSetDueDate: (ids: string[], date: Date | null) => Promise<void>;
}

export function useActionItems(): UseActionItemsReturn {
  const [items, setItems] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // First paint only. A later refetch (cache invalidation after delete/snooze)
  // must not flip `loading` — TaskHub unmounts the list when `loading` is true
  // even if `items` is already populated.
  const hasLoadedRef = useRef(false);

  // One list read at a time. Each successful delete invalidates the action-items
  // cache, so bulk-deleting N tasks asked for N reloads at once. Past the backend's
  // 12 list reads per minute the extra reads were 429ed and the page showed that
  // error although every delete had succeeded; and whichever read answered last
  // won, even one that predated a later delete, so deleted tasks came back. A
  // reload requested while one is in flight now shares it and queues one more read.
  const fetchInFlightRef = useRef<Promise<void> | null>(null);
  const refetchQueuedRef = useRef(false);

  // Read the task list once
  const loadItems = useCallback(async () => {
    try {
      if (!hasLoadedRef.current) {
        setLoading(true);
      }
      setError(null);
      const { items: data } = await getActionItems({ limit: 500 });
      // Another reload was requested while this read was in flight, usually
      // because a delete committed, so this answer can still list that task.
      // Keep what is shown; the queued read replaces it.
      if (refetchQueuedRef.current && hasLoadedRef.current) return;
      // Ensure we always set an array
      setItems(Array.isArray(data) ? data : []);
      hasLoadedRef.current = true;
    } catch (err) {
      console.error('Failed to fetch action items:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tasks');
      if (!hasLoadedRef.current) {
        setItems([]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch action items
  const fetchItems = useCallback((): Promise<void> => {
    if (fetchInFlightRef.current) {
      refetchQueuedRef.current = true;
      return fetchInFlightRef.current;
    }
    const run = (async () => {
      try {
        do {
          refetchQueuedRef.current = false;
          await loadItems();
        } while (refetchQueuedRef.current);
      } finally {
        fetchInFlightRef.current = null;
      }
    })();
    fetchInFlightRef.current = run;
    return run;
  }, [loadItems]);

  // Initial fetch
  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Subscribe to cache invalidation - refetch when action items are modified elsewhere
  useEffect(() => {
    const unsubscribe = onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.actionItems) {
        fetchItems();
      }
    });
    return unsubscribe;
  }, [fetchItems]);

  // Group items
  const groupedItems = useMemo(() => groupActionItems(items), [items]);

  // Calculate stats
  const stats = useMemo(() => {
    const completed = items.filter((i) => i.completed).length;
    const pending = items.filter((i) => !i.completed).length;
    const overdue = groupedItems.overdue.length;
    const noDueDateCount = groupedItems.noDueDate.length;
    const todayItems = items.filter((i) => i.due_at && daysUntilDue(i.due_at) === 0);
    const todayCompleted = todayItems.filter((i) => i.completed).length;

    // Calculate weekly stats (last 7 days)
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    const weekItems = items.filter((i) => {
      if (!i.due_at) return false;
      const dueDate = new Date(i.due_at);
      dueDate.setHours(0, 0, 0, 0);
      return dueDate >= weekAgo && dueDate <= today;
    });
    const weekCompleted = weekItems.filter((i) => i.completed).length;
    const weekPending = weekItems.filter((i) => !i.completed).length;

    // Calculate streak (consecutive days with at least one completion)
    let streak = 0;
    const checkDate = new Date(today);

    // Check if we completed anything today first
    const todayHasCompletion = items.some((i) => {
      if (!i.completed || !i.completed_at) return false;
      const completedDate = new Date(i.completed_at);
      return completedDate.toDateString() === today.toDateString();
    });

    if (todayHasCompletion) {
      streak = 1;
      checkDate.setDate(checkDate.getDate() - 1);

      // Count backwards from yesterday
      while (true) {
        const dateStr = checkDate.toDateString();
        const hasCompletion = items.some((i) => {
          if (!i.completed || !i.completed_at) return false;
          const completedDate = new Date(i.completed_at);
          return completedDate.toDateString() === dateStr;
        });

        if (hasCompletion) {
          streak++;
          checkDate.setDate(checkDate.getDate() - 1);
        } else {
          break;
        }

        // Safety limit
        if (streak > 365) break;
      }
    }

    return {
      total: items.length,
      completed,
      pending,
      overdue,
      noDueDateCount,
      todayTotal: todayItems.length,
      todayCompleted,
      weekCompleted,
      weekPending,
      streak,
    };
  }, [items, groupedItems]);

  // Generate week data for calendar strip
  const weekData = useMemo(() => {
    const days: UseActionItemsReturn['weekData'] = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let i = 0; i < 7; i++) {
      const date = new Date(today);
      date.setDate(date.getDate() + i);

      const counts = getTaskCountsForDate(items, date);

      days.push({
        date,
        dayName:
          i === 0
            ? 'TODAY'
            : date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase(),
        dayNumber: date.getDate(),
        isToday: i === 0,
        pending: counts.pending,
        completed: counts.completed,
      });
    }

    return days;
  }, [items]);

  // Sorted flat list for list view (pending sorted by due date, no-date items last)
  const sortedFlatList = useMemo(() => {
    const pending = items.filter((i) => !i.completed);
    const completed = items.filter((i) => i.completed);

    // Sort pending: by due date (soonest first), items without due date go last
    pending.sort((a, b) => {
      // Handle no due date (goes last)
      if (!a.due_at && !b.due_at) {
        // Both no due date: sort by created_at (newest first)
        const aCreated = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bCreated = b.created_at ? new Date(b.created_at).getTime() : 0;
        return bCreated - aCreated;
      }
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;

      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });

    // Sort completed by completion date (most recent first)
    completed.sort((a, b) => {
      const aCompleted = a.completed_at ? new Date(a.completed_at).getTime() : 0;
      const bCompleted = b.completed_at ? new Date(b.completed_at).getTime() : 0;
      return bCompleted - aCompleted;
    });

    return { pending, completed };
  }, [items]);

  // Add new item
  const addItem = useCallback(
    async (params: CreateActionItemParams): Promise<ActionItem | null> => {
      try {
        const newItem = await createActionItem(params);
        setItems((prev) => prependOrReplaceById(prev, newItem));
        return newItem;
      } catch (err) {
        console.error('Failed to create action item:', err);
        setError(err instanceof Error ? err.message : 'Failed to create task');
        return null;
      }
    },
    [],
  );

  // Toggle completion
  const toggleComplete = useCallback(
    async (id: string, completed: boolean) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;

      // Optimistic update
      setItems((prev) =>
        prev.map((i) =>
          i.id === id
            ? {
                ...i,
                completed,
                completed_at: completed ? new Date().toISOString() : null,
              }
            : i,
        ),
      );

      try {
        await toggleActionItemCompleted(id, completed);
      } catch (err) {
        console.error('Failed to toggle completion:', err);
        // Revert on error to the values this toggle replaced, so a task that
        // fails to reopen keeps the date it was completed on
        setItems((prev) =>
          prev.map((i) =>
            i.id === id
              ? { ...i, completed: item.completed, completed_at: item.completed_at }
              : i,
          ),
        );
        setError(err instanceof Error ? err.message : 'Failed to update task');
      }
    },
    [items],
  );

  // Snooze (add days to due date)
  const snooze = useCallback(
    async (id: string, days: number) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;

      const newDate = new Date();
      if (item.due_at) {
        const currentDate = new Date(item.due_at);
        // If current date is in the past, start from today
        if (currentDate < newDate) {
          newDate.setDate(newDate.getDate() + days);
        } else {
          newDate.setTime(currentDate.getTime());
          newDate.setDate(newDate.getDate() + days);
        }
      } else {
        newDate.setDate(newDate.getDate() + days);
      }

      // Optimistic update
      const newDueAt = newDate.toISOString();
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, due_at: newDueAt } : i)));

      try {
        await updateActionItemDueDate(id, newDueAt);
      } catch (err) {
        console.error('Failed to snooze task:', err);
        // Revert on error
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, due_at: item.due_at } : i)),
        );
        setError(err instanceof Error ? err.message : 'Failed to snooze task');
      }
    },
    [items],
  );

  // Set specific due date
  const setDueDate = useCallback(
    async (id: string, date: Date | null) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;

      const newDueAt = date ? date.toISOString() : null;

      // Optimistic update
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, due_at: newDueAt } : i)));

      try {
        await updateActionItemDueDate(id, newDueAt);
      } catch (err) {
        console.error('Failed to update due date:', err);
        // Revert on error
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, due_at: item.due_at } : i)),
        );
        setError(err instanceof Error ? err.message : 'Failed to update due date');
      }
    },
    [items],
  );

  // Update description
  const updateDescription = useCallback(
    async (id: string, description: string) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;

      const oldDescription = item.description;

      // Optimistic update
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, description } : i)));

      try {
        await updateActionItemDescription(id, description);
      } catch (err) {
        console.error('Failed to update description:', err);
        // Revert on error
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, description: oldDescription } : i)),
        );
        setError(err instanceof Error ? err.message : 'Failed to update task');
      }
    },
    [items],
  );

  // Remove item
  const removeItem = useCallback(
    async (id: string) => {
      const item = items.find((i) => i.id === id);
      if (!item) return;

      // Optimistic update
      setItems((prev) => prev.filter((i) => i.id !== id));

      try {
        await deleteActionItem(id);
      } catch (err) {
        console.error('Failed to delete task:', err);
        // Revert on error
        setItems((prev) => [...prev, item]);
        setError(err instanceof Error ? err.message : 'Failed to delete task');
      }
    },
    [items],
  );

  // Bulk complete
  const bulkComplete = useCallback(
    async (ids: string[]) => {
      // Optimistic update
      setItems((prev) =>
        prev.map((item) =>
          ids.includes(item.id)
            ? { ...item, completed: true, completed_at: new Date().toISOString() }
            : item,
        ),
      );

      try {
        await Promise.all(ids.map((id) => toggleActionItemCompleted(id, true)));
      } catch (err) {
        console.error('Failed to bulk complete:', err);
        // Refresh to get correct state
        fetchItems();
        setError(err instanceof Error ? err.message : 'Failed to complete tasks');
      }
    },
    [fetchItems],
  );

  // Bulk delete
  const bulkDelete = useCallback(
    async (ids: string[]) => {
      const deletedItems = items.filter((i) => ids.includes(i.id));

      // Optimistic update
      setItems((prev) => prev.filter((i) => !ids.includes(i.id)));

      const results = await Promise.allSettled(ids.map((id) => deleteActionItem(id)));
      const failedIds = new Set(
        ids.filter((_, index) => results[index].status === 'rejected'),
      );

      if (failedIds.size > 0) {
        console.error(
          'Failed to bulk delete:',
          results.filter((r) => r.status === 'rejected'),
        );
        // Only restore the tasks whose delete failed; tasks the server
        // already deleted must stay gone.
        setItems((prev) => [...prev, ...deletedItems.filter((i) => failedIds.has(i.id))]);
        setError('Failed to delete some tasks');
      }
    },
    [items],
  );

  // Bulk snooze
  const bulkSnooze = useCallback(
    async (ids: string[], days: number) => {
      const newDate = new Date();
      newDate.setDate(newDate.getDate() + days);
      const newDueAt = newDate.toISOString();

      // Optimistic update
      setItems((prev) =>
        prev.map((item) =>
          ids.includes(item.id) ? { ...item, due_at: newDueAt } : item,
        ),
      );

      try {
        await Promise.all(ids.map((id) => updateActionItemDueDate(id, newDueAt)));
      } catch (err) {
        console.error('Failed to bulk snooze:', err);
        // Refresh to get correct state
        fetchItems();
        setError(err instanceof Error ? err.message : 'Failed to snooze tasks');
      }
    },
    [fetchItems],
  );

  // Bulk set due date (for no-due-date items)
  const bulkSetDueDate = useCallback(
    async (ids: string[], date: Date | null) => {
      const newDueAt = date ? date.toISOString() : null;

      // Optimistic update
      setItems((prev) =>
        prev.map((item) =>
          ids.includes(item.id) ? { ...item, due_at: newDueAt } : item,
        ),
      );

      try {
        await Promise.all(ids.map((id) => updateActionItemDueDate(id, newDueAt)));
      } catch (err) {
        console.error('Failed to bulk set due date:', err);
        // Refresh to get correct state
        fetchItems();
        setError(err instanceof Error ? err.message : 'Failed to set due dates');
      }
    },
    [fetchItems],
  );

  return {
    items,
    groupedItems,
    loading,
    error,
    sortedFlatList,
    stats,
    weekData,
    refresh: fetchItems,
    addItem,
    toggleComplete,
    snooze,
    setDueDate,
    updateDescription,
    removeItem,
    bulkComplete,
    bulkDelete,
    bulkSnooze,
    bulkSetDueDate,
  };
}
