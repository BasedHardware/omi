/**
 * Daily auto-goal-generation scheduler + stale-goal cleanup.
 *
 * Swift reference: `desktop/Desktop/Sources/ProactiveAssistants/Assistants/Goals/GoalGenerationService.swift`
 *
 * Responsibilities:
 * 1. `onConversationSaved` — fired whenever a conversation finishes uploading.
 *    If auto-generation is enabled, remove stale AI goals (no progress in
 *    3+ days) and run the daily-generation check.
 * 2. `generateNow` — manual "Generate AI Goal" trigger that bypasses the
 *    once-per-day gate and retries up to 3× with backoff.
 *
 * We never run on a timer — generation is always conversation-driven so the
 * model has fresh context to mine.
 */

import { api } from "@/services/api";
import { notify } from "@/services/notifications";
import { suggestGoal } from "@/services/goalsAIService";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { useGoalSettingsStore } from "@/stores/goalSettingsStore";
import { useAuthStore } from "@/stores/authStore";

const MAX_ACTIVE_AI_GOALS = 3;
const STALE_DAYS = 3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function daysSince(iso: string | null | undefined): number {
  if (!iso) return 0;
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return 0;
  return (Date.now() - then) / 86_400_000;
}

async function removeStaleGoals(): Promise<void> {
  const goals = useGoalStore.getState().goals;
  for (const goal of goals) {
    if (goal.source !== "ai") continue;
    if (!goal.is_active) continue;
    if (daysSince(goal.updated_at) < STALE_DAYS) continue;
    console.info(
      `[goalGen] completing stale AI goal '${goal.title}' (no update in ${Math.floor(
        daysSince(goal.updated_at),
      )} days)`,
    );
    try {
      await api.delete(`/v1/goals/${goal.id}`);
      await useGoalStore.getState().loadGoals(true);
    } catch (err) {
      console.warn("[goalGen] stale-goal cleanup failed:", err);
    }
  }
}

async function generateGoalOnce(): Promise<boolean> {
  const token = useAuthStore.getState().idToken;
  if (!token) return false;

  await useGoalStore.getState().loadGoals(true);
  const activeAi = useGoalStore
    .getState()
    .goals.filter((g) => g.source === "ai" && g.is_active);

  if (activeAi.length >= MAX_ACTIVE_AI_GOALS) {
    console.info(
      `[goalGen] already have ${activeAi.length}/${MAX_ACTIVE_AI_GOALS} AI goals, skipping`,
    );
    useGoalSettingsStore.getState().setLastGenerationDate(new Date().toISOString());
    return true;
  }

  const suggestion = await suggestGoal();
  if (!suggestion || !suggestion.suggested_title) {
    console.info("[goalGen] suggestGoal returned nothing");
    return false;
  }

  const created = await useGoalStore.getState().createGoal({
    title: suggestion.suggested_title,
    goal_type: suggestion.suggested_type,
    target_value: suggestion.suggested_target,
    current_value: 0,
    min_value: suggestion.suggested_min,
    max_value: suggestion.suggested_max,
    source: "ai",
  });

  if (!created) return false;

  useGoalSettingsStore.getState().setLastGenerationDate(new Date().toISOString());
  console.info(`[goalGen] created AI goal '${created.title}'`);
  void notify("New Goal", created.title);
  return true;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Hook to fire after a conversation has been saved/uploaded. */
export async function onConversationSaved(): Promise<void> {
  const { autoGenerateEnabled, lastGenerationDate } =
    useGoalSettingsStore.getState();
  if (!autoGenerateEnabled) return;

  await removeStaleGoals();

  // Daily-generation gate: skip if we already generated on this calendar day.
  if (lastGenerationDate) {
    const last = new Date(lastGenerationDate);
    if (Number.isFinite(last.getTime()) && sameLocalDay(last, new Date())) {
      return;
    }
  }

  await generateGoalOnce();
}

/** Manual trigger — used by the "Generate AI Goal" button. */
export async function generateNow(): Promise<Goal | null> {
  useGoalStore.getState().setGenerating(true);
  try {
    await removeStaleGoals();
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const ok = await generateGoalOnce();
      if (ok) {
        const latest = useGoalStore
          .getState()
          .goals.find((g) => g.source === "ai");
        return latest ?? null;
      }
      if (attempt < 2) await new Promise((r) => setTimeout(r, 5000));
    }
    return null;
  } finally {
    useGoalStore.getState().setGenerating(false);
  }
}
