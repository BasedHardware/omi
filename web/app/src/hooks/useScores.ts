'use client';

import { getScores } from '@/lib/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import type { Scores } from '@/types/scores';
import { t } from '@/lib/i18n';

export interface UseScoresReturn {
  scores: Scores | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useScores(): UseScoresReturn {
  const { data, loading, error, refresh } = useAsyncResource('scores', getScores, {
    fallbackMessage: t('Failed to load scores'),
  });

  return { scores: data ?? null, loading, error, refresh };
}
