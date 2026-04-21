/**
 * Goal-related user preferences. Persisted to `goal-settings.json` via
 * tauri-plugin-store so they survive across restarts. Mirrors Swift's
 * UserDefaults keys `goalGeneration_autoEnabled` and `goalGeneration_lastDate`.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { LazyStore } from "@tauri-apps/plugin-store";

const tauriStore = new LazyStore("goal-settings.json");

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

interface GoalSettingsState {
  autoGenerateEnabled: boolean;
  /** ISO string of the last successful daily generation, or null. */
  lastGenerationDate: string | null;

  setAutoGenerateEnabled: (v: boolean) => void;
  setLastGenerationDate: (iso: string | null) => void;
}

export const useGoalSettingsStore = create<GoalSettingsState>()(
  persist(
    (set) => ({
      autoGenerateEnabled: false,
      lastGenerationDate: null,

      setAutoGenerateEnabled: (v) => set({ autoGenerateEnabled: v }),
      setLastGenerationDate: (iso) => set({ lastGenerationDate: iso }),
    }),
    {
      name: "goal-settings",
      storage: tauriStorage,
    },
  ),
);
