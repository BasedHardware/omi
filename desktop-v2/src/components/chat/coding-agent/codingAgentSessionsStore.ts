/**
 * Zustand store for coding-agent session listing.
 *
 * Mirrors the `chatStore` persist pattern using Tauri's `LazyStore` adapter so
 * the session list survives app restarts without a JSONL re-scan on every mount.
 * A `refresh()` call replaces the in-memory list from the Rust command.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { invoke } from "@tauri-apps/api/core";
import { LazyStore } from "@tauri-apps/plugin-store";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CodingAgentSessionMeta {
  id: string;
  filePath: string;
  cwd: string;
  name?: string;
  createdAt: number;
  modifiedAt: number;
  messageCount: number;
}

interface CodingAgentSessionsState {
  sessions: CodingAgentSessionMeta[];
  currentFilePath: string | null;
  /** Folder the active session is operating against. Lifted out of
   *  CodingAgentSession's local state so picking a session from the sidebar
   *  also updates the folder pill. Survives app restart via persist. */
  currentCwd: string | null;
  refresh: (folder?: string) => Promise<void>;
  selectSession: (filePath: string | null, cwd?: string | null) => void;
  setCurrentCwd: (cwd: string | null) => void;
  rename: (filePath: string, name: string) => Promise<void>;
  remove: (filePath: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Tauri store adapter (same pattern as chatStore.ts:128-143)
// ---------------------------------------------------------------------------

const tauriStore = new LazyStore("coding-agent-sessions.json");

const tauriStorage = createJSONStorage(() => ({
  getItem: async (name: string) => {
    const val = await tauriStore.get<string>(name);
    return val ?? null;
  },
  setItem: async (name: string, value: string) => {
    await tauriStore.set(name, value);
    await tauriStore.save();
  },
  removeItem: async (name: string) => {
    await tauriStore.delete(name);
    await tauriStore.save();
  },
}));

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useCodingAgentSessionsStore = create<CodingAgentSessionsState>()(
  persist(
    (set, _get) => ({
      sessions: [],
      currentFilePath: null,
      currentCwd: null,

      refresh: async (folder?: string) => {
        const sessions = await invoke<CodingAgentSessionMeta[]>(
          "coding_agent_list_sessions",
          { folder },
        );
        set({ sessions });
      },

      selectSession: (filePath: string | null, cwd?: string | null) => {
        set((s) => ({
          currentFilePath: filePath,
          currentCwd: cwd === undefined ? s.currentCwd : cwd,
        }));
      },

      setCurrentCwd: (cwd: string | null) => set({ currentCwd: cwd }),

      rename: async (filePath: string, name: string) => {
        await invoke("coding_agent_rename_session", { filePath, name });
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.filePath === filePath ? { ...sess, name } : sess,
          ),
        }));
      },

      remove: async (filePath: string) => {
        await invoke("coding_agent_delete_session", { filePath });
        set((s) => ({
          sessions: s.sessions.filter((sess) => sess.filePath !== filePath),
          currentFilePath:
            s.currentFilePath === filePath ? null : s.currentFilePath,
        }));
      },
    }),
    {
      name: "coding-agent-sessions",
      storage: tauriStorage,
      // Only persist the list and the current pointer; actions are not serialisable.
      partialize: (s) => ({
        sessions: s.sessions,
        currentFilePath: s.currentFilePath,
        currentCwd: s.currentCwd,
      }),
    },
  ),
);
