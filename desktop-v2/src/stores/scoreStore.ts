/**
 * Score store — computes daily / weekly / overall productivity scores from
 * `/v1/action-items`.
 *
 * The old local Rust backend exposed `/v1/scores`, but the remote Nooto API
 * does not have that endpoint. We compute the same buckets client-side by
 * querying action items filtered by `due_start_date` / `due_end_date`.
 *
 * Score formula (matches Swift `ScoreWidget` / old Rust `get_scores`):
 *   score = total > 0 ? (completed / total) * 100 : 0
 *
 * Buckets:
 *   - daily:   due between 00:00 and 23:59 today
 *   - weekly:  due in the last 7 days (today inclusive)
 *   - overall: all action items ever (no date filter)
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

interface MinimalActionItem {
  completed?: boolean;
}

interface ActionItemsResponse {
  action_items?: MinimalActionItem[];
  has_more?: boolean;
}

const EMPTY_BUCKET: ScoreBucket = { score: 0, completed_tasks: 0, total_tasks: 0 };
const STALE_MS = 60_000;
const MAX_PAGE_LIMIT = 500;

function bucketFromItems(items: MinimalActionItem[]): ScoreBucket {
  const total = items.length;
  const completed = items.reduce((acc, item) => acc + (item.completed ? 1 : 0), 0);
  const score = total > 0 ? (completed / total) * 100 : 0;
  return { score, completed_tasks: completed, total_tasks: total };
}

async function fetchActionItems(params: Record<string, string>): Promise<MinimalActionItem[]> {
  const all: MinimalActionItem[] = [];
  let offset = 0;
  while (true) {
    const qs = new URLSearchParams({
      ...params,
      limit: String(MAX_PAGE_LIMIT),
      offset: String(offset),
    }).toString();
    const data = await api.get<ActionItemsResponse>(`/v1/action-items?${qs}`);
    const items = data?.action_items ?? [];
    all.push(...items);
    if (!data?.has_more || items.length === 0) break;
    offset += items.length;
  }
  return all;
}

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
      const now = new Date();
      const todayStart = new Date(now);
      todayStart.setHours(0, 0, 0, 0);
      const todayEnd = new Date(now);
      todayEnd.setHours(23, 59, 59, 999);
      const weekStart = new Date(todayStart);
      weekStart.setDate(weekStart.getDate() - 6);

      const [dailyItems, weeklyItems, overallItems] = await Promise.all([
        fetchActionItems({
          due_start_date: todayStart.toISOString(),
          due_end_date: todayEnd.toISOString(),
        }),
        fetchActionItems({
          due_start_date: weekStart.toISOString(),
          due_end_date: todayEnd.toISOString(),
        }),
        fetchActionItems({}),
      ]);

      set({
        scores: {
          daily: bucketFromItems(dailyItems),
          weekly: bucketFromItems(weeklyItems),
          overall: bucketFromItems(overallItems),
        },
        isLoading: false,
        lastFetchedAt: Date.now(),
      });
    } catch (err) {
      console.warn("[ScoreStore] loadScores failed:", err);
      set({
        scores: {
          daily: EMPTY_BUCKET,
          weekly: EMPTY_BUCKET,
          overall: EMPTY_BUCKET,
        },
        isLoading: false,
        lastFetchedAt: Date.now(),
      });
    }
  },
}));
