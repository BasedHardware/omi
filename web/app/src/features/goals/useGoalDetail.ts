'use client';

import { useCallback, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { getGoalAdvice, getGoalHistory } from '@/features/goals/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { useRequestOwner } from '@/hooks/useRequestOwner';
import { useSignalValue } from '@/lib/signals';
import type { GoalHistoryEntry } from '@/types/goals';

export interface UseGoalDetailReturn {
  history: GoalHistoryEntry[];
  historyLoading: boolean;
  historyError: string | null;
  advice: string | null;
  adviceLoading: boolean;
  adviceError: string | null;
  requestAdvice: () => Promise<void>;
}

const NO_HISTORY: GoalHistoryEntry[] = [];

export function createGoalAdviceStore() {
  const advice = createSignal<string | null>(null);
  const loading = createSignal(false);
  const error = createSignal<string | null>(null);
  return { advice, loading, error };
}

/**
 * History for one goal, plus advice fetched only on demand.
 *
 * Advice is an LLM call behind a server-side rate limit, so it never runs on
 * open — only when the user asks for it. A new store per goal id drops in-flight
 * writes the way `useRequestOwner` does: the previous goal's response cannot
 * land under the newly selected title.
 */
export function useGoalDetail(goalId: string | null): UseGoalDetailReturn {
  const history = useAsyncResource(
    goalId,
    useCallback(() => getGoalHistory(goalId as string), [goalId]),
    { fallbackMessage: 'Failed to load history' },
  );

  const store = useMemo(() => createGoalAdviceStore(), [goalId]);
  const claimRequest = useRequestOwner(goalId);

  const advice = useSignalValue(store.advice);
  const adviceLoading = useSignalValue(store.loading);
  const adviceError = useSignalValue(store.error);

  const requestAdvice = useCallback(async () => {
    if (!goalId) return;
    const isCurrent = claimRequest();
    store.loading.set(true);
    store.error.set(null);
    try {
      const result = await getGoalAdvice(goalId);
      if (!isCurrent()) return;
      store.advice.set(result);
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to load goal advice:', err);
      store.error.set(err instanceof Error ? err.message : 'Failed to load advice');
    } finally {
      if (isCurrent()) store.loading.set(false);
    }
  }, [goalId, claimRequest, store]);

  return {
    history: history.data ?? NO_HISTORY,
    historyLoading: history.loading,
    historyError: history.error,
    advice,
    adviceLoading,
    adviceError,
    requestAdvice,
  };
}
