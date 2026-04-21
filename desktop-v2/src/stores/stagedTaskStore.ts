/**
 * Staged tasks store — wraps the local SQLite staged-tasks table behind a
 * Zustand store. Staged tasks are AI-extracted from screenshots, sitting in
 * a review queue before they get promoted to real tasks (action items).
 *
 * Data flow:
 * - Source of truth: local SQLite (`staged_tasks` table, see
 *   `staged_tasks_db.rs`). Populated by `taskAssistant.ts` and pruned by
 *   `taskDeduplicationService.ts`.
 * - This store reads via `get_staged_tasks` and exposes promote/dismiss
 *   helpers used by `TasksPage`.
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { api } from "@/services/api";

export interface StagedTask {
  id: string;
  description: string;
  priority: string | null;
  tags_json: string | null;
  due_at: string | null;
  confidence: number | null;
  source_app: string | null;
  window_title: string | null;
  context_summary: string | null;
  current_activity: string | null;
  metadata_json: string | null;
  relevance_score: number | null;
  screenshot_id: number | null;
  created_at: string;
  updated_at: string;
  backend_id: string | null;
  deleted: boolean;
  completed: boolean;
}

interface StagedTaskState {
  staged: StagedTask[];
  isLoading: boolean;
  loadStaged: () => Promise<void>;
  /** Hard-delete locally + mirror to backend. */
  dismissStaged: (id: string) => Promise<void>;
  /** Mark completed locally — caller is responsible for creating the real task. */
  promoteStaged: (id: string) => Promise<void>;
}

export const useStagedTaskStore = create<StagedTaskState>((set, get) => ({
  staged: [],
  isLoading: false,

  loadStaged: async () => {
    set({ isLoading: true });
    try {
      const rows = await invoke<StagedTask[]>("get_staged_tasks", { limit: 200 });
      set({ staged: rows, isLoading: false });
    } catch (err) {
      console.warn("[StagedTaskStore] load failed:", err);
      set({ isLoading: false });
    }
  },

  dismissStaged: async (id: string) => {
    const task = get().staged.find((t) => t.id === id);
    set({ staged: get().staged.filter((t) => t.id !== id) });
    try {
      await invoke("delete_staged_task", { id, hard: true });
    } catch (err) {
      console.warn("[StagedTaskStore] local delete failed:", err);
    }
    if (task?.backend_id) {
      try {
        await api.delete(`/v1/staged-tasks/${task.backend_id}`);
      } catch (err) {
        console.warn("[StagedTaskStore] backend delete failed:", err);
      }
    }
  },

  promoteStaged: async (id: string) => {
    set({ staged: get().staged.filter((t) => t.id !== id) });
    try {
      await invoke("set_staged_task_completed", { id, completed: true });
    } catch (err) {
      console.warn("[StagedTaskStore] mark completed failed:", err);
    }
  },
}));
