import type {
  GoalHistoryEntryResponse,
  GoalMetric,
  GoalResponse,
  GoalSource,
  GoalStatus,
  GoalType,
} from '@/lib/omiApi.generated';

export type { GoalMetric, GoalResponse, GoalSource, GoalStatus, GoalType };

/** A goal as the web client consumes it. */
export type Goal = GoalResponse;

/** One recorded progress value, from `/v1/goals/{id}/history`. */
export type GoalHistoryEntry = GoalHistoryEntryResponse;
