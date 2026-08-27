import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';
import {
  invalidateCache,
  invalidationPatterns,
  fetchWithCache,
  cacheKeys,
  CACHE_TTL,
} from '@/lib/cache';
import {
  API_BASE_URL,
  fetchAuthorizedBlob,
  fetchWithAuth,
  getAudioAuthHeaders,
} from '@/shared/api/client';
import type { Goal, GoalHistoryEntry } from '@/types/goals';

export async function getGoals(includeEnded = false): Promise<Goal[]> {
  const goals = await fetchWithAuth<Goal[]>(
    `/v1/goals/all?include_ended=${includeEnded}`,
  );
  return Array.isArray(goals) ? goals : [];
}

/**
 * Create body, matching what the desktop apps send
 * (`desktop/windows/src/renderer/src/pages/Goals.tsx` saveNew): title, a
 * required positive target, and unit only when the user gave one.
 *
 * `target_value` is required — the backend 422s without it — so a title-only
 * goal defaults to 1, which completes on a single tick.
 */
export interface CreateGoalParams {
  title: string;
  target_value: number;
  unit?: string;
}

export async function createGoal(params: CreateGoalParams): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>('/v1/goals', {
    method: 'POST',
    body: JSON.stringify(params),
  });
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

/**
 * Update only a goal's progress value.
 *
 * The backend takes `current_value` as a query parameter on this route, not in
 * the body.
 */
export async function updateGoalProgress(
  id: string,
  currentValue: number,
): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>(
    `/v1/goals/${id}/progress?current_value=${encodeURIComponent(currentValue)}`,
    { method: 'PATCH' },
  );
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

export interface UpdateGoalParams {
  title?: string;
  target_value?: number;
  current_value?: number;
  unit?: string | null;
}

export async function updateGoal(id: string, updates: UpdateGoalParams): Promise<Goal> {
  const goal = await fetchWithAuth<Goal>(`/v1/goals/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
  invalidateCache(invalidationPatterns.goals);
  return goal;
}

export async function deleteGoal(id: string): Promise<void> {
  await fetchWithAuth(`/v1/goals/${id}`, { method: 'DELETE' });
  invalidateCache(invalidationPatterns.goals);
}

/**
 * Recorded progress values for a goal, newest window first.
 *
 * Uses `/v1/goals/{id}/history`, not `/v1/goals/{id}/detail`. The detail
 * projection and the progress-events feed both sit behind
 * `require_canonical_task_user`, which 404s for anyone not enrolled in the
 * canonical task system — most web users.
 */
export async function getGoalHistory(id: string, days = 30): Promise<GoalHistoryEntry[]> {
  const history = await fetchWithAuth<GoalHistoryEntry[]>(
    `/v1/goals/${id}/history?days=${days}`,
  );
  return Array.isArray(history) ? history : [];
}

/** AI-generated advice for a goal. Rate limited server-side. */
export async function getGoalAdvice(id: string): Promise<string> {
  const response = await fetchWithAuth<{ advice: string }>(`/v1/goals/${id}/advice`);
  return response.advice;
}

// ============================================================================

/** Daily, weekly, and overall task-completion scores. */
