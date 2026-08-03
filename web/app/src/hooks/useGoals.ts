'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createGoal,
  deleteGoal,
  getGoals,
  updateGoalProgress,
  type CreateGoalParams,
} from '@/lib/api';
import { sortGoals } from '@/lib/goals';
import type { Goal } from '@/types/goals';

export interface UseGoalsReturn {
  goals: Goal[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addGoal: (params: CreateGoalParams) => Promise<Goal | null>;
  setProgress: (id: string, currentValue: number) => Promise<void>;
  removeGoal: (id: string) => Promise<void>;
}

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export function useGoals(): UseGoalsReturn {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * The last committed goal list.
   *
   * Rollback has to read the pre-write value at call time. Capturing it inside
   * a `setGoals` updater does not work: React runs the updater during the next
   * render, which is after a rejected request's `catch` has already run, so the
   * captured value would still be undefined and the rollback would silently
   * do nothing.
   */
  const committed = useRef<Goal[]>(goals);

  useEffect(() => {
    committed.current = goals;
  }, [goals]);

  const load = useCallback(async (isMounted: () => boolean) => {
    try {
      const loaded = await getGoals();
      if (!isMounted()) return;
      setGoals(loaded);
      setError(null);
    } catch (err) {
      console.error('Failed to load goals:', err);
      if (!isMounted()) return;
      setError(messageFor(err, 'Failed to load goals'));
    } finally {
      if (isMounted()) setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await load(() => true);
  }, [load]);

  // The initial load starts here but every setState happens after an await, so
  // mounting never triggers a synchronous cascading render, and a request that
  // lands after unmount is dropped.
  useEffect(() => {
    let mounted = true;
    void load(() => mounted);
    return () => {
      mounted = false;
    };
  }, [load]);

  const addGoal = useCallback(async (params: CreateGoalParams): Promise<Goal | null> => {
    try {
      const created = await createGoal(params);
      setGoals((current) => [...current, created]);
      setError(null);
      return created;
    } catch (err) {
      console.error('Failed to create goal:', err);
      setError(messageFor(err, 'Failed to create goal'));
      return null;
    }
  }, []);

  /**
   * Apply a server write optimistically and roll the row back if it fails, so a
   * rejected write never leaves the UI showing a value the server does not have.
   */
  const applyOptimistic = useCallback(
    async (
      id: string,
      optimistic: (goal: Goal) => Goal,
      request: () => Promise<Goal>,
      failureMessage: string,
    ) => {
      const previous = committed.current.find((goal) => goal.id === id);
      setGoals((current) =>
        current.map((goal) => (goal.id === id ? optimistic(goal) : goal)),
      );

      try {
        const updated = await request();
        setGoals((current) => current.map((goal) => (goal.id === id ? updated : goal)));
        setError(null);
      } catch (err) {
        console.error(failureMessage, err);
        if (previous) {
          const restored = previous;
          setGoals((current) =>
            current.map((goal) => (goal.id === id ? restored : goal)),
          );
        }
        setError(messageFor(err, failureMessage));
      }
    },
    [],
  );

  const setProgress = useCallback(
    async (id: string, currentValue: number) => {
      await applyOptimistic(
        id,
        (goal) => ({ ...goal, current_value: currentValue }),
        () => updateGoalProgress(id, currentValue),
        'Failed to update progress',
      );
    },
    [applyOptimistic],
  );

  const removeGoal = useCallback(async (id: string) => {
    const removed = committed.current.find((goal) => goal.id === id);
    setGoals((current) => current.filter((goal) => goal.id !== id));

    try {
      await deleteGoal(id);
      setError(null);
    } catch (err) {
      console.error('Failed to delete goal:', err);
      if (removed) {
        const restored = removed;
        setGoals((current) => [...current, restored]);
      }
      setError(messageFor(err, 'Failed to delete goal'));
    }
  }, []);

  const sorted = useMemo(() => sortGoals(goals), [goals]);

  return {
    goals: sorted,
    loading,
    error,
    refresh,
    addGoal,
    setProgress,
    removeGoal,
  };
}
