'use client';

import { useCallback, useEffect, useState } from 'react';
import { getScores } from '@/lib/api';
import type { Scores } from '@/types/goals';

export interface UseScoresReturn {
  scores: Scores | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useScores(): UseScoresReturn {
  const [scores, setScores] = useState<Scores | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isMounted: () => boolean) => {
    try {
      const loaded = await getScores();
      if (!isMounted()) return;
      setScores(loaded);
      setError(null);
    } catch (err) {
      console.error('Failed to load scores:', err);
      if (!isMounted()) return;
      setError(err instanceof Error ? err.message : 'Failed to load scores');
    } finally {
      if (isMounted()) setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await load(() => true);
  }, [load]);

  // Every setState runs after an await, so mounting does not trigger a
  // synchronous cascading render, and a late response after unmount is dropped.
  useEffect(() => {
    let mounted = true;
    void load(() => mounted);
    return () => {
      mounted = false;
    };
  }, [load]);

  return { scores, loading, error, refresh };
}
