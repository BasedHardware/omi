/**
 * Goals store — local-first with backend reconciliation.
 *
 * Data flow matches Swift's DashboardViewModel + GoalStorage:
 * - Read local SQLite first for instant paint (no network wait)
 * - Fetch `/v1/goals/all` in parallel
 * - Call `sync_server_goals` Rust command to reconcile (upsert + mark-absent-as-deleted)
 * - Re-read local to surface the reconciled state
 *
 * Writes go optimistic (update state immediately) → backend → local upsert →
 * rollback-on-error. Progress updates that cross the target value emit a
 * celebration event via `goalCelebrationStore` (added in Phase 4).
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { useAuthStore } from "./authStore";
import { api } from "@/services/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type GoalType = "boolean" | "scale" | "numeric";

export interface Goal {
  /** Stable local-or-backend id. Backend-synced goals use `backend_id` as their id. */
  id: string;
  title: string;
  description?: string | null;
  goal_type: GoalType;
  target_value: number;
  current_value: number;
  min_value: number;
  max_value: number;
  unit?: string | null;
  is_active: boolean;
  completed_at?: string | null;
  /** Local-only provenance marker: "user" | "ai" | "onboarding_step_flow". */
  source?: string | null;
  backend_id?: string | null;
  backend_synced: boolean;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

/** The shape the backend returns on GET/POST/PATCH. */
interface ServerGoal {
  id: string;
  title: string;
  description?: string | null;
  goal_type: GoalType;
  target_value: number;
  current_value: number;
  min_value: number;
  max_value: number;
  unit?: string | null;
  is_active: boolean;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateGoalInput {
  title: string;
  description?: string | null;
  goal_type?: GoalType;
  target_value?: number;
  current_value?: number;
  min_value?: number;
  max_value?: number;
  unit?: string | null;
  source?: "user" | "ai" | "onboarding_step_flow";
}

export interface UpdateGoalPatch {
  title?: string;
  description?: string | null;
  target_value?: number;
  current_value?: number;
  min_value?: number;
  max_value?: number;
  unit?: string | null;
}

interface GoalState {
  goals: Goal[];
  completedGoals: Goal[];
  isLoading: boolean;
  isGenerating: boolean;
  lastFetchedAt: number | null;
  loadGoals: (force?: boolean) => Promise<void>;
  loadCompletedGoals: () => Promise<void>;
  createGoal: (input: CreateGoalInput) => Promise<Goal | null>;
  updateGoal: (id: string, patch: UpdateGoalPatch) => Promise<void>;
  updateGoalProgress: (id: string, currentValue: number) => Promise<void>;
  deleteGoal: (id: string) => Promise<void>;
  setGenerating: (v: boolean) => void;
  clearLocal: () => Promise<void>;
}

const STALE_MS = 30_000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toGoal(src: ServerGoal, source?: string | null): Goal {
  return {
    id: src.id,
    title: src.title,
    description: src.description ?? null,
    goal_type: src.goal_type,
    target_value: src.target_value,
    current_value: src.current_value,
    min_value: src.min_value,
    max_value: src.max_value,
    unit: src.unit ?? null,
    is_active: src.is_active,
    completed_at: src.completed_at ?? null,
    source: source ?? null,
    backend_id: src.id,
    backend_synced: true,
    deleted: false,
    created_at: src.created_at,
    updated_at: src.updated_at,
  };
}

function isCompletion(before: Goal | undefined, after: Goal): boolean {
  if (!before) return false;
  if (before.completed_at) return false;
  if (after.completed_at) return true;
  // Server may auto-complete boolean goals when current_value reaches target.
  return (
    before.current_value < before.target_value &&
    after.current_value >= after.target_value
  );
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useGoalStore = create<GoalState>((set, get) => ({
  goals: [],
  completedGoals: [],
  isLoading: false,
  isGenerating: false,
  lastFetchedAt: null,

  loadGoals: async (force = false) => {
    const state = get();
    if (!force && state.lastFetchedAt != null && Date.now() - state.lastFetchedAt < STALE_MS) {
      return;
    }

    set({ isLoading: true });

    // 1. Paint from local immediately.
    try {
      const local = await invoke<Goal[]>("get_goals");
      set({ goals: local });
    } catch (err) {
      console.warn("[GoalStore] local read failed:", err);
    }

    // 2. Fetch from backend (skip if not signed in).
    const token = useAuthStore.getState().idToken;
    if (!token) {
      set({ isLoading: false, lastFetchedAt: Date.now() });
      return;
    }

    try {
      const serverGoals = await api.get<ServerGoal[]>("/v1/goals/all");
      const serverList = Array.isArray(serverGoals) ? serverGoals : [];

      // 3. Reconcile into local.
      await invoke("sync_server_goals", {
        goals: serverList.map((g) => ({
          id: g.id,
          backend_id: g.id,
          backend_synced: true,
          title: g.title,
          description: g.description ?? null,
          goal_type: g.goal_type,
          target_value: g.target_value,
          current_value: g.current_value,
          min_value: g.min_value,
          max_value: g.max_value,
          unit: g.unit ?? null,
          is_active: g.is_active,
          completed_at: g.completed_at ?? null,
          source: null,
        })),
      });

      // 4. Re-read local for final state.
      const reconciled = await invoke<Goal[]>("get_goals");
      set({ goals: reconciled, isLoading: false, lastFetchedAt: Date.now() });
    } catch (err) {
      console.warn("[GoalStore] backend sync failed, keeping local:", err);
      set({ isLoading: false, lastFetchedAt: Date.now() });
    }
  },

  loadCompletedGoals: async () => {
    try {
      const local = await invoke<Goal[]>("get_completed_goals", { limit: 100 });
      set({ completedGoals: local });
    } catch (err) {
      console.warn("[GoalStore] local completed read failed:", err);
    }

    const token = useAuthStore.getState().idToken;
    if (!token) return;

    try {
      const server = await api.get<ServerGoal[] | { goals: ServerGoal[] }>(
        "/v1/goals/completed",
      );
      const list = Array.isArray(server) ? server : server?.goals ?? [];
      const mapped = list.map((g) => toGoal(g));

      // Persist to local so the history page works offline.
      for (const g of mapped) {
        await invoke("upsert_goal", {
          input: {
            id: g.id,
            backend_id: g.id,
            backend_synced: true,
            title: g.title,
            description: g.description ?? null,
            goal_type: g.goal_type,
            target_value: g.target_value,
            current_value: g.current_value,
            min_value: g.min_value,
            max_value: g.max_value,
            unit: g.unit ?? null,
            is_active: false,
            completed_at: g.completed_at ?? new Date().toISOString(),
            source: null,
          },
        }).catch(() => {});
      }

      const reconciled = await invoke<Goal[]>("get_completed_goals", { limit: 100 });
      set({ completedGoals: reconciled });
    } catch (err) {
      // History endpoint may not exist in all backends — degrade gracefully.
      console.warn("[GoalStore] completed goals fetch failed:", err);
    }
  },

  createGoal: async (input) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return null;

    const body = {
      title: input.title,
      goal_type: input.goal_type ?? "scale",
      target_value: input.target_value ?? 10,
      current_value: input.current_value ?? 0,
      min_value: input.min_value ?? 0,
      max_value: input.max_value ?? 10,
      unit: input.unit ?? null,
    };

    try {
      const created = await api.post<ServerGoal>("/v1/goals", body);
      const goal = toGoal(created, input.source ?? "user");

      // Persist source locally (backend doesn't store it yet).
      await invoke("upsert_goal", {
        input: {
          id: goal.id,
          backend_id: goal.id,
          backend_synced: true,
          title: goal.title,
          description: goal.description ?? null,
          goal_type: goal.goal_type,
          target_value: goal.target_value,
          current_value: goal.current_value,
          min_value: goal.min_value,
          max_value: goal.max_value,
          unit: goal.unit ?? null,
          is_active: goal.is_active,
          completed_at: goal.completed_at ?? null,
          source: input.source ?? "user",
        },
      });

      // Respect 4-goal cap by re-reading local (backend auto-deactivates oldest).
      const reconciled = await invoke<Goal[]>("get_goals");
      set({ goals: reconciled });
      return goal;
    } catch (err) {
      console.error("[GoalStore] createGoal failed:", err);
      return null;
    }
  },

  updateGoal: async (id, patch) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const prev = get().goals;
    const current = prev.find((g) => g.id === id);
    if (!current) return;

    // Optimistic.
    set({
      goals: prev.map((g) => (g.id === id ? { ...g, ...patch } : g)),
    });

    try {
      const updated = await api.patch<ServerGoal>(`/v1/goals/${id}`, patch);
      const next = toGoal(updated, current.source ?? null);
      await invoke("upsert_goal", {
        input: {
          id: next.id,
          backend_id: next.id,
          backend_synced: true,
          title: next.title,
          description: next.description ?? null,
          goal_type: next.goal_type,
          target_value: next.target_value,
          current_value: next.current_value,
          min_value: next.min_value,
          max_value: next.max_value,
          unit: next.unit ?? null,
          is_active: next.is_active,
          completed_at: next.completed_at ?? null,
          source: current.source ?? null,
        },
      });
      set({ goals: get().goals.map((g) => (g.id === id ? next : g)) });
    } catch (err) {
      console.error("[GoalStore] updateGoal failed:", err);
      set({ goals: prev });
    }
  },

  updateGoalProgress: async (id, currentValue) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const prev = get().goals;
    const current = prev.find((g) => g.id === id);
    if (!current) return;

    // Optimistic.
    set({
      goals: prev.map((g) => (g.id === id ? { ...g, current_value: currentValue } : g)),
    });
    await invoke("update_goal_progress", { id, currentValue }).catch(() => {});

    try {
      const updated = await api.patch<ServerGoal>(
        `/v1/goals/${id}/progress?current_value=${currentValue}`,
        {},
      );
      const next = toGoal(updated, current.source ?? null);

      await invoke("upsert_goal", {
        input: {
          id: next.id,
          backend_id: next.id,
          backend_synced: true,
          title: next.title,
          description: next.description ?? null,
          goal_type: next.goal_type,
          target_value: next.target_value,
          current_value: next.current_value,
          min_value: next.min_value,
          max_value: next.max_value,
          unit: next.unit ?? null,
          is_active: next.is_active,
          completed_at: next.completed_at ?? null,
          source: current.source ?? null,
        },
      });
      await invoke("insert_goal_progress_history", {
        goalId: id,
        value: currentValue,
      }).catch(() => {});

      // Detect completion → emit event for the celebration overlay.
      if (isCompletion(current, next)) {
        const mod = await import("./goalCelebrationStore");
        mod.useGoalCelebrationStore.getState().celebrate(next);
      }

      if (next.is_active) {
        set({ goals: get().goals.map((g) => (g.id === id ? next : g)) });
      } else {
        // Goal was auto-completed server-side — remove from active list,
        // fall through to completed list on next load.
        set({
          goals: get().goals.filter((g) => g.id !== id),
          completedGoals: [next, ...get().completedGoals],
        });
      }
    } catch (err) {
      console.error("[GoalStore] updateGoalProgress failed:", err);
      set({ goals: prev });
    }
  },

  deleteGoal: async (id) => {
    const prev = get().goals;
    set({ goals: prev.filter((g) => g.id !== id) });
    await invoke("soft_delete_goal", { id }).catch(() => {});

    const token = useAuthStore.getState().idToken;
    if (!token) return;

    try {
      await api.delete(`/v1/goals/${id}`);
    } catch (err) {
      console.error("[GoalStore] deleteGoal failed:", err);
      // Note: the local soft-delete stands; next sync will pick up truth.
    }
  },

  setGenerating: (v) => set({ isGenerating: v }),

  clearLocal: async () => {
    try {
      await invoke("clear_goals_db");
    } catch (err) {
      console.warn("[GoalStore] clearLocal failed:", err);
    }
    set({ goals: [], completedGoals: [], lastFetchedAt: null });
  },
}));
