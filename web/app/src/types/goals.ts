import type {
  GoalMetric,
  GoalResponse,
  GoalSource,
  GoalStatus,
  GoalType,
} from '@/lib/omiApi.generated';

export type { GoalMetric, GoalResponse, GoalSource, GoalStatus, GoalType };

/** A goal as the web client consumes it. */
export type Goal = GoalResponse;

/**
 * Score wire shapes for `/v1/scores` and `/v1/daily-score`.
 *
 * These live here rather than in `omiApi.generated.ts` because the scores
 * router is absent from `docs/api-reference/app-client-openapi.json`, which is
 * what the generator reads. Keep in sync with `backend/models/score.py`.
 */
export interface ScorePeriod {
  score: number;
  completed_tasks: number;
  total_tasks: number;
}

export type ScoreTab = 'daily' | 'weekly' | 'overall';

export interface Scores {
  daily: ScorePeriod;
  weekly: ScorePeriod;
  overall: ScorePeriod;
  default_tab: string;
  date: string;
}

export interface DailyScore {
  date: string;
  score: number;
  completed_tasks: number;
  total_tasks: number;
}
