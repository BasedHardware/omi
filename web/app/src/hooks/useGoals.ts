'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import {
  createGoal,
  deleteGoal,
  getGoals,
  updateGoal,
  updateGoalProgress,
  type CreateGoalParams,
  type UpdateGoalParams,
} from '@/lib/api';
import { sortGoals } from '@/lib/goals';
import type { Goal } from '@/types/goals';

export interface UseGoalsReturn {
  goals: Goal[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addGoal: (params: CreateGoalParams) => Promise<Goal | null>;
  editGoal: (id: string, updates: UpdateGoalParams) => Promise<boolean>;
  setProgress: (id: string, currentValue: number) => Promise<boolean>;
  removeGoal: (id: string) => Promise<boolean>;
}

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/**
 * The goal list and its mutations, held in moonshine signals.
 *
 * A `createResource` would cover the load but is read-only, and this list is
 * written optimistically. Signals also let rollback read the committed value
 * synchronously at call time — capturing it inside a React state updater does
 * not work, because React runs updaters during the next render, after a
 * rejected request's `catch` has already run.
 */
export function createGoalsStore() {
  const goals = createSignal<Goal[]>([]);
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
      goals.set(await getGoals());
      error.set(null);
    } catch (err) {
      console.error('Failed to load goals:', err);
      error.set(messageFor(err, 'Failed to load goals'));
    } finally {
      loading.set(false);
    }
  };

  /** Apply a write optimistically and put the old row back if it fails. */
  const optimistic = async (
    id: string,
    apply: (goal: Goal) => Goal,
    request: () => Promise<Goal>,
    failureMessage: string,
  ): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const previous = goals.peek().find((goal) => goal.id === id);
      goals.set((current) =>
        current.map((goal) => (goal.id === id ? apply(goal) : goal)),
      );

      try {
        const updated = await request();
        goals.set((current) => current.map((goal) => (goal.id === id ? updated : goal)));
        error.set(null);
        return true;
      } catch (err) {
        console.error(failureMessage, err);
        if (previous) {
          goals.set((current) =>
            current.map((goal) => (goal.id === id ? previous : goal)),
          );
        }
        error.set(messageFor(err, failureMessage));
        return false;
      }
    });

  const add = async (params: CreateGoalParams): Promise<Goal | null> => {
    try {
      const created = await createGoal(params);
      goals.set((current) => [...current, created]);
      error.set(null);
      return created;
    } catch (err) {
      console.error('Failed to create goal:', err);
      error.set(messageFor(err, 'Failed to create goal'));
      return null;
    }
  };

  const remove = (id: string): Promise<boolean> =>
    enqueueMutation(id, async () => {
      const removed = goals.peek().find((goal) => goal.id === id);
      goals.set((current) => current.filter((goal) => goal.id !== id));

      try {
        await deleteGoal(id);
        error.set(null);
        return true;
      } catch (err) {
        console.error('Failed to delete goal:', err);
        if (removed) {
          goals.set((current) => [...current, removed]);
        }
        error.set(messageFor(err, 'Failed to delete goal'));
        return false;
      }
    });

  return { goals, loading, error, load, optimistic, add, remove };
}

export function useGoals(): UseGoalsReturn {
  const store = useMemo(() => createGoalsStore(), []);

  // Loaded here rather than from the factory: useMemo may run more than once
  // per commit (StrictMode renders twice), and loading in the factory would
  // fetch once per discarded store. This writes signals, not React state.
  useEffect(() => {
    void store.load();
  }, [store]);

  const goals = useSignalValue(store.goals);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);

  const editGoal = useCallback(
    (id: string, updates: UpdateGoalParams) =>
      store.optimistic(
        id,
        (goal) => ({
          ...goal,
          title: updates.title ?? goal.title,
          target_value: updates.target_value ?? goal.target_value,
          unit: updates.unit !== undefined ? updates.unit : goal.unit,
        }),
        () => updateGoal(id, updates),
        'Failed to update goal',
      ),
    [store],
  );

  const setProgress = useCallback(
    (id: string, currentValue: number) =>
      store.optimistic(
        id,
        (goal) => ({ ...goal, current_value: currentValue }),
        () => updateGoalProgress(id, currentValue),
        'Failed to update progress',
      ),
    [store],
  );

  const sorted = useMemo(() => sortGoals(goals), [goals]);

  return {
    goals: sorted,
    loading,
    error,
    refresh: store.load,
    addGoal: store.add,
    editGoal,
    setProgress,
    removeGoal: store.remove,
  };
}
