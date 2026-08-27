'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
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

  // Fetch action items
  const fetchItems = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const { items: data } = await getActionItems({ limit: 500 });
      // Ensure we always set an array
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch action items:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tasks');
      setItems([]); // Reset to empty array on error
    } finally {
      setLoading(false);
    }
  }, []);

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
    const completed = items.filter(i => i.completed).length;
    const pending = items.filter(i => !i.completed).length;
    const overdue = groupedItems.overdue.length;
    const noDueDateCount = groupedItems.noDueDate.length;
    const todayItems = items.filter(i => i.due_at && isSameLocalDay(new Date(i.due_at)));
    const todayCompleted = todayItems.filter(i => i.completed).length;

    // Calculate weekly stats (last 7 days)
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    const weekItems = items.filter(i => {
      if (!i.due_at) return false;
      const dueDate = new Date(i.due_at);
      dueDate.setHours(0, 0, 0, 0);
      return dueDate >= weekAgo && dueDate <= today;
    });
    const weekCompleted = weekItems.filter(i => i.completed).length;
    const weekPending = weekItems.filter(i => !i.completed).length;

    // Calculate streak (consecutive days with at least one completion)
    let streak = 0;
    const checkDate = new Date(today);

    // Check if we completed anything today first
    const todayHasCompletion = items.some(i => {
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
        const hasCompletion = items.some(i => {
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
        dayName: i === 0 ? 'TODAY' : date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase(),
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
    const pending = items.filter(i => !i.completed);
    const completed = items.filter(i => i.completed);

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
  const addItem = useCallback(async (params: CreateActionItemParams): Promise<ActionItem | null> => {
    try {
      const newItem = await createActionItem(params);
      setItems(prev => [newItem, ...prev]);
      return newItem;
    } catch (err) {
      console.error('Failed to create action item:', err);
      setError(err instanceof Error ? err.message : 'Failed to create task');
      return null;
    }
  }, []);

  // Toggle completion
  const toggleComplete = useCallback(async (id: string, completed: boolean) => {
    // Optimistic update
    setItems(prev =>
      prev.map(item =>
        item.id === id
          ? { ...item, completed, completed_at: completed ? new Date().toISOString() : null }
          : item
      )
    );

    try {
      await toggleActionItemCompleted(id, completed);
    } catch (err) {
      console.error('Failed to toggle completion:', err);
      // Revert on error
      setItems(prev =>
        prev.map(item =>
          item.id === id ? { ...item, completed: !completed, completed_at: null } : item
        )
      );
      setError(err instanceof Error ? err.message : 'Failed to update task');
    }
  }, []);

  // Snooze (add days to due date)
  const snooze = useCallback(async (id: string, days: number) => {
    const item = items.find(i => i.id === id);
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
    setItems(prev =>
      prev.map(i => (i.id === id ? { ...i, due_at: newDueAt } : i))
    );

    try {
      await updateActionItemDueDate(id, newDueAt);
    } catch (err) {
      console.error('Failed to snooze task:', err);
      // Revert on error
      setItems(prev =>
        prev.map(i => (i.id === id ? { ...i, due_at: item.due_at } : i))
      );
      setError(err instanceof Error ? err.message : 'Failed to snooze task');
    }
  }, [items]);

  // Set specific due date
  const setDueDate = useCallback(async (id: string, date: Date | null) => {
    const item = items.find(i => i.id === id);
    if (!item) return;

    const newDueAt = date ? date.toISOString() : null;

    // Optimistic update
    setItems(prev =>
      prev.map(i => (i.id === id ? { ...i, due_at: newDueAt } : i))
    );

    try {
      await updateActionItemDueDate(id, newDueAt);
    } catch (err) {
      console.error('Failed to update due date:', err);
      // Revert on error
      setItems(prev =>
        prev.map(i => (i.id === id ? { ...i, due_at: item.due_at } : i))
      );
      setError(err instanceof Error ? err.message : 'Failed to update due date');
    }
  }, [items]);

  // Update description
  const updateDescription = useCallback(async (id: string, description: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;

    const oldDescription = item.description;

    // Optimistic update
    setItems(prev =>
      prev.map(i => (i.id === id ? { ...i, description } : i))
    );

    try {
      await updateActionItemDescription(id, description);
    } catch (err) {
      console.error('Failed to update description:', err);
      // Revert on error
      setItems(prev =>
        prev.map(i => (i.id === id ? { ...i, description: oldDescription } : i))
      );
      setError(err instanceof Error ? err.message : 'Failed to update task');
    }
  }, [items]);

  // Remove item
  const removeItem = useCallback(async (id: string) => {
    const item = items.find(i => i.id === id);
    if (!item) return;

    // Optimistic update
    setItems(prev => prev.filter(i => i.id !== id));

    try {
      await deleteActionItem(id);
    } catch (err) {
      console.error('Failed to delete task:', err);
      // Revert on error
      setItems(prev => [...prev, item]);
      setError(err instanceof Error ? err.message : 'Failed to delete task');
    }
  }, [items]);

  // Bulk complete
  const bulkComplete = useCallback(async (ids: string[]) => {
    // Optimistic update
    setItems(prev =>
      prev.map(item =>
        ids.includes(item.id)
          ? { ...item, completed: true, completed_at: new Date().toISOString() }
          : item
      )
    );

    try {
      await Promise.all(ids.map(id => toggleActionItemCompleted(id, true)));
    } catch (err) {
      console.error('Failed to bulk complete:', err);
      // Refresh to get correct state
      fetchItems();
      setError(err instanceof Error ? err.message : 'Failed to complete tasks');
    }
  }, [fetchItems]);

  // Bulk delete
  const bulkDelete = useCallback(async (ids: string[]) => {
    const deletedItems = items.filter(i => ids.includes(i.id));

    // Optimistic update
    setItems(prev => prev.filter(i => !ids.includes(i.id)));

    try {
      await Promise.all(ids.map(id => deleteActionItem(id)));
    } catch (err) {
      console.error('Failed to bulk delete:', err);
      // Revert on error
      setItems(prev => [...prev, ...deletedItems]);
      setError(err instanceof Error ? err.message : 'Failed to delete tasks');
    }
  }, [items]);

  // Bulk snooze
  const bulkSnooze = useCallback(async (ids: string[], days: number) => {
    const newDate = new Date();
    newDate.setDate(newDate.getDate() + days);
    const newDueAt = newDate.toISOString();

    // Optimistic update
    setItems(prev =>
      prev.map(item =>
        ids.includes(item.id) ? { ...item, due_at: newDueAt } : item
      )
    );

    try {
      await Promise.all(ids.map(id => updateActionItemDueDate(id, newDueAt)));
    } catch (err) {
      console.error('Failed to bulk snooze:', err);
      // Refresh to get correct state
      fetchItems();
      setError(err instanceof Error ? err.message : 'Failed to snooze tasks');
    }
  }, [fetchItems]);

  // Bulk set due date (for no-due-date items)
  const bulkSetDueDate = useCallback(async (ids: string[], date: Date | null) => {
    const newDueAt = date ? date.toISOString() : null;

    // Optimistic update
    setItems(prev =>
      prev.map(item =>
        ids.includes(item.id) ? { ...item, due_at: newDueAt } : item
      )
    );

    try {
      await Promise.all(ids.map(id => updateActionItemDueDate(id, newDueAt)));
    } catch (err) {
      console.error('Failed to bulk set due date:', err);
      // Refresh to get correct state
      fetchItems();
      setError(err instanceof Error ? err.message : 'Failed to set due dates');
    }
  }, [fetchItems]);

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
