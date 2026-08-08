'use client';

import { useCallback, useMemo, useState } from 'react';
import { getGoalAdvice, getGoalHistory } from '@/lib/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { useRequestOwner } from '@/hooks/useRequestOwner';
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

/**
 * History for one goal, plus advice fetched only on demand.
 *
 * Advice is an LLM call behind a server-side rate limit, so it never runs on
 * open — only when the user asks for it. It is therefore plain state rather
 * than a resource, which would fetch eagerly.
 */
export function useGoalDetail(goalId: string | null): UseGoalDetailReturn {
  const history = useAsyncResource(
    goalId,
    useCallback(() => getGoalHistory(goalId as string), [goalId]),
    { fallbackMessage: 'Failed to load history' },
  );

  const [advice, setAdvice] = useState<string | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState<string | null>(null);
  const [adviceGoalId, setAdviceGoalId] = useState<string | null>(goalId);

  // Advice belongs to the goal it was requested for; drop it when the
  // selection changes rather than showing it under a new title. The in-flight
  // request goes with it: the new goal starts idle, not stuck behind the old
  // goal's pending call.
  if (goalId !== adviceGoalId) {
    setAdviceGoalId(goalId);
    setAdvice(null);
    setAdviceError(null);
    setAdviceLoading(false);
  }

  const claimRequest = useRequestOwner(goalId);

  const requestAdvice = useCallback(async () => {
    if (!goalId) return;
    const isCurrent = claimRequest();
    setAdviceLoading(true);
    setAdviceError(null);
    try {
      const result = await getGoalAdvice(goalId);
      if (!isCurrent()) return;
      setAdvice(result);
    } catch (err) {
      if (!isCurrent()) return;
      console.error('Failed to load goal advice:', err);
      setAdviceError(err instanceof Error ? err.message : 'Failed to load advice');
    } finally {
      if (isCurrent()) setAdviceLoading(false);
    }
  }, [goalId, claimRequest]);

  return useMemo(
    () => ({
      history: history.data ?? NO_HISTORY,
      historyLoading: history.loading,
      historyError: history.error,
      advice,
      adviceLoading,
      adviceError,
      requestAdvice,
    }),
    [
      history.data,
      history.loading,
      history.error,
      advice,
      adviceLoading,
      adviceError,
      requestAdvice,
    ],
  );
}
