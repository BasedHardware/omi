/**
 * Score wire shapes for `/v1/scores` and `/v1/daily-score`.
 *
 * Hand-written rather than generated: the scores router is absent from
 * `docs/api-reference/app-client-openapi.json`, which is what
 * `omiApi.generated.ts` is built from. Keep in sync with
 * `backend/models/score.py`.
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
