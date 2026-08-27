'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import {
  getActionItems,
  createActionItem,
  toggleActionItemCompleted,
  updateActionItemDueDate,
  updateActionItemDescription,
  deleteActionItem,
  type CreateActionItemParams,
} from '@/features/tasks/api';
import { onCacheInvalidation, invalidationPatterns } from '@/lib/cache';
import type { ActionItem, GroupedActionItems } from '@/types/conversation';
import { getTaskCountsForDate, groupActionItems, isSameLocalDay } from './model';

export interface UseActionItemsReturn {
  items: ActionItem[];
  groupedItems: GroupedActionItems;
  loading: boolean;
  error: string | null;
  sortedFlatList: {
    pending: ActionItem[];
    completed: ActionItem[];
  };
  stats: {
    total: number;
    completed: number;
    pending: number;
    overdue: number;
    noDueDateCount: number;
    todayTotal: number;
    todayCompleted: number;
    weekCompleted: number;
    weekPending: number;
    streak: number;
  };
  weekData: Array<{
    date: Date;
    dayName: string;
    dayNumber: number;
    isToday: boolean;
    pending: number;
    completed: number;
  }>;
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

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function snoozeDueAt(dueAt: string | null | undefined, days: number): string {
  const newDate = new Date();
  if (dueAt) {
    const currentDate = new Date(dueAt);
    if (currentDate < newDate) {
      newDate.setDate(newDate.getDate() + days);
    } else {
      newDate.setTime(currentDate.getTime());
      newDate.setDate(newDate.getDate() + days);
    }
  } else {
    newDate.setDate(newDate.getDate() + days);
  }
  return newDate.toISOString();
}

/**
 * The task list and its mutations, held in moonshine signals.
 *
 * Same reason as `createGoalsStore`: optimistic writes need `signal.peek()` so
 * rollback can read the committed row at call time, not from a React updater
 * that has not run yet.
 */
export function createActionItemsStore() {
  const items = createSignal<ActionItem[]>([]);
  const loading = createSignal(true);
  const error = createSignal<string | null>(null);
  const mutationTails = new Map<string, Promise<void>>();

  const enqueueMutation = <T>(id: string, mutation: () => Promise<T>): Promise<T> => {
    const previous = mutationTails.get(id);
    const result = previous ? previous.then(mutation) : mutation();
    const tail = result.then(
      () => undefined,
      () => undefined,
    );
    mutationTails.set(id, tail);
    void tail.then(() => {
      if (mutationTails.get(id) === tail) mutationTails.delete(id);
    });
    return result;
  };

  const load = async () => {
    loading.set(true);
    try {
      const { items: data } = await getActionItems({ limit: 500 });
      items.set(Array.isArray(data) ? data : []);
      error.set(null);
    } catch (err) {
      console.error('Failed to fetch action items:', err);
      error.set(messageFor(err, 'Failed to load tasks'));
      items.set([]);
    } finally {
      loading.set(false);
    }
  };

  const patch = async (
    id: string,
    apply: (item: ActionItem) => ActionItem,
    request: () => Promise<void>,
    failureMessage: string,
  ): Promise<void> =>
    enqueueMutation(id, async () => {
      const previous = items.peek().find((item) => item.id === id);
      if (!previous) return;
      items.set((current) =>
        current.map((item) => (item.id === id ? apply(previous) : item)),
      );

      try {
        await request();
        error.set(null);
      } catch (err) {
        console.error(failureMessage, err);
        items.set((current) =>
          current.map((item) => (item.id === id ? previous : item)),
        );
        error.set(messageFor(err, failureMessage));
      }
    });

  const add = async (params: CreateActionItemParams): Promise<ActionItem | null> => {
    try {
      const created = await createActionItem(params);
      items.set((current) => [created, ...current]);
      error.set(null);
      return created;
    } catch (err) {
      console.error('Failed to create action item:', err);
      error.set(messageFor(err, 'Failed to create task'));
      return null;
    }
  };

  const toggleComplete = (id: string, completed: boolean) =>
    patch(
      id,
      (item) => ({
        ...item,
        completed,
        completed_at: completed ? new Date().toISOString() : null,
      }),
      () => toggleActionItemCompleted(id, completed),
      'Failed to update task',
    );

  const snooze = (id: string, days: number) =>
    patch(
      id,
      (item) => ({ ...item, due_at: snoozeDueAt(item.due_at, days) }),
      () => {
        const current = items.peek().find((item) => item.id === id);
        return updateActionItemDueDate(id, current?.due_at ?? null);
      },
      'Failed to snooze task',
    );

  const setDueDate = (id: string, date: Date | null) => {
    const newDueAt = date ? date.toISOString() : null;
    return patch(
      id,
      (item) => ({ ...item, due_at: newDueAt }),
      () => updateActionItemDueDate(id, newDueAt),
      'Failed to update due date',
    );
  };

  const updateDescription = (id: string, description: string) =>
    patch(
      id,
      (item) => ({ ...item, description }),
      () => updateActionItemDescription(id, description),
      'Failed to update task',
    );

  const remove = (id: string): Promise<void> =>
    enqueueMutation(id, async () => {
      const removed = items.peek().find((item) => item.id === id);
      if (!removed) return;
      items.set((current) => current.filter((item) => item.id !== id));

      try {
        await deleteActionItem(id);
        error.set(null);
      } catch (err) {
        console.error('Failed to delete task:', err);
        items.set((current) => [...current, removed]);
        error.set(messageFor(err, 'Failed to delete task'));
      }
    });

  const bulkComplete = async (ids: string[]) => {
    const previous = items.peek();
    items.set((current) =>
      current.map((item) =>
        ids.includes(item.id)
          ? { ...item, completed: true, completed_at: new Date().toISOString() }
          : item,
      ),
    );
    try {
      await Promise.all(ids.map((id) => toggleActionItemCompleted(id, true)));
      error.set(null);
    } catch (err) {
      console.error('Failed to bulk complete:', err);
      items.set(previous);
      error.set(messageFor(err, 'Failed to complete tasks'));
    }
  };

  const bulkDelete = async (ids: string[]) => {
    const previous = items.peek();
    items.set((current) => current.filter((item) => !ids.includes(item.id)));
    try {
      await Promise.all(ids.map((id) => deleteActionItem(id)));
      error.set(null);
    } catch (err) {
      console.error('Failed to bulk delete:', err);
      items.set(previous);
      error.set(messageFor(err, 'Failed to delete tasks'));
    }
  };

  const bulkSnooze = async (ids: string[], days: number) => {
    const previous = items.peek();
    const newDate = new Date();
    newDate.setDate(newDate.getDate() + days);
    const newDueAt = newDate.toISOString();
    items.set((current) =>
      current.map((item) => (ids.includes(item.id) ? { ...item, due_at: newDueAt } : item)),
    );
    try {
      await Promise.all(ids.map((id) => updateActionItemDueDate(id, newDueAt)));
      error.set(null);
    } catch (err) {
      console.error('Failed to bulk snooze:', err);
      items.set(previous);
      error.set(messageFor(err, 'Failed to snooze tasks'));
    }
  };

  const bulkSetDueDate = async (ids: string[], date: Date | null) => {
    const previous = items.peek();
    const newDueAt = date ? date.toISOString() : null;
    items.set((current) =>
      current.map((item) => (ids.includes(item.id) ? { ...item, due_at: newDueAt } : item)),
    );
    try {
      await Promise.all(ids.map((id) => updateActionItemDueDate(id, newDueAt)));
      error.set(null);
    } catch (err) {
      console.error('Failed to bulk set due date:', err);
      items.set(previous);
      error.set(messageFor(err, 'Failed to set due dates'));
    }
  };

  return {
    items,
    loading,
    error,
    load,
    add,
    toggleComplete,
    snooze,
    setDueDate,
    updateDescription,
    remove,
    bulkComplete,
    bulkDelete,
    bulkSnooze,
    bulkSetDueDate,
  };
}

export function useActionItems(): UseActionItemsReturn {
  const store = useMemo(() => createActionItemsStore(), []);

  useEffect(() => {
    void store.load();
  }, [store]);

  useEffect(() => {
    return onCacheInvalidation((pattern) => {
      if (pattern === invalidationPatterns.actionItems) {
        void store.load();
      }
    });
  }, [store]);

  const items = useSignalValue(store.items);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);

  const groupedItems = useMemo(() => groupActionItems(items), [items]);

  const stats = useMemo(() => {
    const completed = items.filter((i) => i.completed).length;
    const pending = items.filter((i) => !i.completed).length;
    const overdue = groupedItems.overdue.length;
    const noDueDateCount = groupedItems.noDueDate.length;
    const todayItems = items.filter(
      (i) => i.due_at && isSameLocalDay(new Date(i.due_at)),
    );
    const todayCompleted = todayItems.filter((i) => i.completed).length;

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

    let streak = 0;
    const checkDate = new Date(today);
    const todayHasCompletion = items.some((i) => {
      if (!i.completed || !i.completed_at) return false;
      return new Date(i.completed_at).toDateString() === today.toDateString();
    });

    if (todayHasCompletion) {
      streak = 1;
      checkDate.setDate(checkDate.getDate() - 1);
      while (true) {
        const dateStr = checkDate.toDateString();
        const hasCompletion = items.some((i) => {
          if (!i.completed || !i.completed_at) return false;
          return new Date(i.completed_at).toDateString() === dateStr;
        });
        if (hasCompletion) {
          streak++;
          checkDate.setDate(checkDate.getDate() - 1);
        } else {
          break;
        }
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
          i === 0 ? 'TODAY' : date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase(),
        dayNumber: date.getDate(),
        isToday: i === 0,
        pending: counts.pending,
        completed: counts.completed,
      });
    }

    return days;
  }, [items]);

  const sortedFlatList = useMemo(() => {
    const pending = items.filter((i) => !i.completed);
    const completed = items.filter((i) => i.completed);

    pending.sort((a, b) => {
      if (!a.due_at && !b.due_at) {
        const aCreated = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bCreated = b.created_at ? new Date(b.created_at).getTime() : 0;
        return bCreated - aCreated;
      }
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });

    completed.sort((a, b) => {
      const aCompleted = a.completed_at ? new Date(a.completed_at).getTime() : 0;
      const bCompleted = b.completed_at ? new Date(b.completed_at).getTime() : 0;
      return bCompleted - aCompleted;
    });

    return { pending, completed };
  }, [items]);

  const toggleComplete = useCallback(
    (id: string, completed: boolean) => store.toggleComplete(id, completed),
    [store],
  );
  const snooze = useCallback((id: string, days: number) => store.snooze(id, days), [store]);
  const setDueDate = useCallback(
    (id: string, date: Date | null) => store.setDueDate(id, date),
    [store],
  );
  const updateDescription = useCallback(
    (id: string, description: string) => store.updateDescription(id, description),
    [store],
  );
  const removeItem = useCallback((id: string) => store.remove(id), [store]);
  const bulkComplete = useCallback((ids: string[]) => store.bulkComplete(ids), [store]);
  const bulkDelete = useCallback((ids: string[]) => store.bulkDelete(ids), [store]);
  const bulkSnooze = useCallback(
    (ids: string[], days: number) => store.bulkSnooze(ids, days),
    [store],
  );
  const bulkSetDueDate = useCallback(
    (ids: string[], date: Date | null) => store.bulkSetDueDate(ids, date),
    [store],
  );

  return {
    items,
    groupedItems,
    loading,
    error,
    sortedFlatList,
    stats,
    weekData,
    refresh: store.load,
    addItem: store.add,
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
