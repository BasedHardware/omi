/**
 * Wraps the backend's AI goal endpoints. All three operations (suggest,
 * advice, extract-progress) are rate-limited server-side at 30/hour per
 * user; we surface 429s via `notify()` rather than retrying.
 *
 * Swift reference: `desktop/Desktop/Sources/ProactiveAssistants/Assistants/Goals/GoalsAIService.swift`.
 */

import { api } from "@/services/api";
import { useGoalStore } from "@/stores/goalStore";
import { notify } from "@/services/notifications";

// ---------------------------------------------------------------------------
// Types — mirror `/home/matheus/togodynamics/omi/backend/routers/goals.py`
// ---------------------------------------------------------------------------

export interface GoalSuggestion {
  suggested_title: string;
  suggested_type: "boolean" | "scale" | "numeric";
  suggested_target: number;
  suggested_min: number;
  suggested_max: number;
  reasoning: string;
}

interface AdviceResponse {
  advice: string;
}

interface ProgressExtractUpdate {
  goal_id: string;
  goal_title: string;
  previous_value: number;
  new_value: number;
  reasoning?: string;
}

interface ProgressExtractResponse {
  updated: boolean;
  updates?: ProgressExtractUpdate[];
  reason?: string;
}

// ---------------------------------------------------------------------------
// Client-side rate limiting (matches backend 30/hr budget).
//
// Tracks timestamps of calls in the last hour; if a new call would exceed the
// budget, we short-circuit with a toast instead of hitting the server.
// ---------------------------------------------------------------------------

const RATE_LIMIT = 30;
const WINDOW_MS = 60 * 60 * 1000;
const buckets: Record<string, number[]> = {};

function checkRateLimit(key: string): boolean {
  const now = Date.now();
  const bucket = (buckets[key] ??= []).filter((t) => now - t < WINDOW_MS);
  buckets[key] = bucket;
  if (bucket.length >= RATE_LIMIT) {
    void notify(
      "Rate limit",
      `Too many ${key} calls. Try again later.`,
    );
    return false;
  }
  bucket.push(now);
  return true;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function suggestGoal(): Promise<GoalSuggestion | null> {
  if (!checkRateLimit("suggest")) return null;
  try {
    return await api.get<GoalSuggestion>("/v1/goals/suggest");
  } catch (err) {
    console.warn("[goalsAI] suggestGoal failed:", err);
    return null;
  }
}

export async function getGoalAdvice(goalId: string): Promise<string | null> {
  if (!checkRateLimit("advice")) return null;
  try {
    const resp = await api.get<AdviceResponse>(`/v1/goals/${goalId}/advice`);
    return resp?.advice ?? null;
  } catch (err) {
    console.warn("[goalsAI] getGoalAdvice failed:", err);
    return null;
  }
}

/**
 * Asks the backend to extract goal progress from free text and bump matching
 * goals. On success we refresh the local store so the UI reflects the new
 * `current_value`. Silent on no-op.
 */
export async function extractProgress(text: string): Promise<void> {
  const trimmed = text.trim();
  if (trimmed.length < 10) return;
  if (!checkRateLimit("extract")) return;

  try {
    const resp = await api.post<ProgressExtractResponse>(
      "/v1/goals/extract-progress",
      { text: trimmed },
    );
    if (resp?.updated && Array.isArray(resp.updates) && resp.updates.length > 0) {
      console.info(
        `[goalsAI] progress extracted for ${resp.updates.length} goal(s)`,
        resp.updates.map((u) => `${u.goal_title}: ${u.previous_value}→${u.new_value}`),
      );
      // Force-refresh so UI shows the bumped value.
      await useGoalStore.getState().loadGoals(true);
    }
  } catch (err) {
    console.warn("[goalsAI] extractProgress failed:", err);
  }
}
