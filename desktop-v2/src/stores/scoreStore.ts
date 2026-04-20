/**
 * Score store — fetches the user's productivity score from `/v1/scores`.
 *
 * Swift source of truth: `APIClient.getScores()` (used by DashboardViewModel).
 * Backend shape (see `backend/database/action_items.py::get_scores`):
 *
 *   {
 *     daily:   { score, completed_tasks, total_tasks },
 *     weekly:  { score, completed_tasks, total_tasks },
 *     overall: { score, completed_tasks, total_tasks },
 *   }
 *
 * The dashboard's DailyScoreWidget displays the *weekly* score (matches the
 * Swift `ScoreWidget` which pulls from `scoreResponse?.weekly`).
 */

import { create } from "zustand";
import { api } from "@/services/api";
import { useAuthStore } from "./authStore";

export interface ScoreBucket {
  score: number;
  completed_tasks: number;
  total_tasks: number;
}

export interface ScoreResponse {
  daily: ScoreBucket;
  weekly: ScoreBucket;
  overall: ScoreBucket;
}

const EMPTY_BUCKET: ScoreBucket = { score: 0, completed_tasks: 0, total_tasks: 0 };

const STALE_MS = 60_000;

interface ScoreState {
  scores: ScoreResponse | null;
  isLoading: boolean;
  lastFetchedAt: number | null;
  loadScores: (force?: boolean) => Promise<void>;
}

export const useScoreStore = create<ScoreState>((set, get) => ({
  scores: null,
  isLoading: false,
  lastFetchedAt: null,

  loadScores: async (force = false) => {
    const { lastFetchedAt } = get();
    if (
      !force &&
      lastFetchedAt != null &&
      Date.now() - lastFetchedAt < STALE_MS
    ) {
      return;
    }

    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });
    try {
      const data = await api.get<Partial<ScoreResponse>>("/v1/scores");
      const normalized: ScoreResponse = {
        daily: data?.daily ?? EMPTY_BUCKET,
        weekly: data?.weekly ?? EMPTY_BUCKET,
        overall: data?.overall ?? EMPTY_BUCKET,
      };
      set({
        scores: normalized,
        isLoading: false,
        lastFetchedAt: Date.now(),
      });
    } catch (err) {
      console.warn("[ScoreStore] loadScores failed:", err);
      set({ isLoading: false, lastFetchedAt: Date.now() });
    }
  },
}));
