/**
 * Tiny event-bus store for goal-completion celebrations.
 *
 * Replaces Swift's `NSNotification.goalCompleted`. `goalStore.updateGoalProgress`
 * calls `celebrate(goal)` when a progress update causes completion; the
 * `GoalCelebrationOverlay` component (Phase 4) subscribes and plays the
 * fullscreen animation, then calls `clear()` when it fades out.
 */

import { create } from "zustand";
import type { Goal } from "./goalStore";

interface GoalCelebrationState {
  queuedGoal: Goal | null;
  /** Recent ids with a 10s debounce so rapid PATCH responses don't double-fire. */
  recentlyCelebrated: Set<string>;
  celebrate: (goal: Goal) => void;
  clear: () => void;
}

const DEBOUNCE_MS = 10_000;

export const useGoalCelebrationStore = create<GoalCelebrationState>((set, get) => ({
  queuedGoal: null,
  recentlyCelebrated: new Set<string>(),

  celebrate: (goal) => {
    const { recentlyCelebrated } = get();
    if (recentlyCelebrated.has(goal.id)) return;
    const next = new Set(recentlyCelebrated);
    next.add(goal.id);
    set({ queuedGoal: goal, recentlyCelebrated: next });
    setTimeout(() => {
      const { recentlyCelebrated } = get();
      if (!recentlyCelebrated.has(goal.id)) return;
      const pruned = new Set(recentlyCelebrated);
      pruned.delete(goal.id);
      set({ recentlyCelebrated: pruned });
    }, DEBOUNCE_MS);
  },

  clear: () => set({ queuedGoal: null }),
}));
