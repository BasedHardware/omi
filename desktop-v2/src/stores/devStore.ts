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
  liveTranscriptWindowEnabled: boolean;
  toggleDeveloperMode: () => void;
  toggleMemoryIndicator: () => void;
  toggleBypassCommercialHours: () => void;
  toggleLiveTranscriptWindow: () => void;
}

export const useDevStore = create<DevState>()(
  persist(
    (set, get) => ({
      developerMode: false,
      memoryIndicatorEnabled: false,
      bypassCommercialHours: false,
      liveTranscriptWindowEnabled: false,

      toggleDeveloperMode: () => {
        const next = !get().developerMode;
        set({
          developerMode: next,
          // Turning dev mode off should also disable any dev-only surface
          // so users don't end up with orphan floating windows they can't
          // control from a UI they can't see.
          memoryIndicatorEnabled: next ? get().memoryIndicatorEnabled : false,
          liveTranscriptWindowEnabled: next
            ? get().liveTranscriptWindowEnabled
            : false,
        });
      },

      toggleMemoryIndicator: () => {
        set({ memoryIndicatorEnabled: !get().memoryIndicatorEnabled });
      },

      toggleBypassCommercialHours: () => {
        set({ bypassCommercialHours: !get().bypassCommercialHours });
      },

      toggleLiveTranscriptWindow: () => {
        set({
          liveTranscriptWindowEnabled: !get().liveTranscriptWindowEnabled,
        });
      },
    }),
    {
      name: "developer-settings",
      storage: tauriStorage,
    },
  ),
);
