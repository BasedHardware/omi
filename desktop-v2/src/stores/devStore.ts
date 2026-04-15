import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { LazyStore } from "@tauri-apps/plugin-store";

const tauriStore = new LazyStore("developer.json");

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

interface DevState {
  developerMode: boolean;
  memoryIndicatorEnabled: boolean;
  bypassCommercialHours: boolean;
  toggleDeveloperMode: () => void;
  toggleMemoryIndicator: () => void;
  toggleBypassCommercialHours: () => void;
}

export const useDevStore = create<DevState>()(
  persist(
    (set, get) => ({
      developerMode: false,
      memoryIndicatorEnabled: false,
      bypassCommercialHours: false,

      toggleDeveloperMode: () => {
        const next = !get().developerMode;
        set({
          developerMode: next,
          memoryIndicatorEnabled: next ? get().memoryIndicatorEnabled : false,
        });
      },

      toggleMemoryIndicator: () => {
        set({ memoryIndicatorEnabled: !get().memoryIndicatorEnabled });
      },

      toggleBypassCommercialHours: () => {
        set({ bypassCommercialHours: !get().bypassCommercialHours });
      },
    }),
    {
      name: "developer-settings",
      storage: tauriStorage,
    },
  ),
);
