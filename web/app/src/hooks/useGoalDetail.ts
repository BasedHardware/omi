'use client';

import { useCallback, useEffect, useState } from 'react';
import { getGoalAdvice, getGoalHistory } from '@/lib/api';
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

/**
 * History for one goal, plus advice fetched only on demand.
 *
 * Advice is an LLM call behind a server-side rate limit, so it never runs on
 * open — only when the user asks for it.
 */
export function useGoalDetail(goalId: string | null): UseGoalDetailReturn {
  const [history, setHistory] = useState<GoalHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<string | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState<string | null>(null);

  const loadHistory = useCallback(async (id: string, isMounted: () => boolean) => {
    try {
      const loaded = await getGoalHistory(id);
      if (!isMounted()) return;
      setHistory(loaded);
      setHistoryError(null);
    } catch (err) {
      console.error('Failed to load goal history:', err);
      if (!isMounted()) return;
      setHistoryError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      if (isMounted()) setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!goalId) {
      setHistory([]);
      setAdvice(null);
      setHistoryError(null);
      setAdviceError(null);
      return;
    }

    let mounted = true;
    setHistoryLoading(true);
    // Advice belongs to the previous goal; drop it when the selection changes.
    setAdvice(null);
    setAdviceError(null);
    void loadHistory(goalId, () => mounted);
    return () => {
      mounted = false;
    };
  }, [goalId, loadHistory]);

  const requestAdvice = useCallback(async () => {
    if (!goalId) return;
    setAdviceLoading(true);
    setAdviceError(null);
    try {
      setAdvice(await getGoalAdvice(goalId));
    } catch (err) {
      console.error('Failed to load goal advice:', err);
      setAdviceError(err instanceof Error ? err.message : 'Failed to load advice');
    } finally {
      setAdviceLoading(false);
    }
  }, [goalId]);

  return {
    history,
    historyLoading,
    historyError,
    advice,
    adviceLoading,
    adviceError,
    requestAdvice,
  };
}
