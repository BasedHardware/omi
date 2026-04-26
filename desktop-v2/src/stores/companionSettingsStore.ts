/**
 * Persistent settings for the Companion feature.
 *
 * Follows the same LazyStore pattern as `devStore.ts`.
 * Stored in `companion-settings.json` via tauri-plugin-store.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { LazyStore } from "@tauri-apps/plugin-store";

const tauriStore = new LazyStore("companion-settings.json");

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

export type CompanionPttKey =
  | "Right Shift"
  | "Fn"
  | "AltGr"
  | "Cmd+Shift"
  | "Cmd+Right Shift";

interface CompanionSettingsState {
  /** When false, companion:start events are ignored (PTT listener still runs). */
  companionEnabled: boolean;
  /** Which key triggers PTT for the companion. Default: Right Shift — rdev
   *  delivers `Key::ShiftRight` reliably on all Mac keyboards; `Fn` is flaky. */
  pttKey: CompanionPttKey;
  /**
   * AVSpeechSynthesisVoice identifier selected by the user.
   * Empty string means "system default" (first voice in the list).
   */
  ttsVoiceId: string;
  /** When true, the pointer ring stays on screen indefinitely after a PTT
   *  answer; any mouse click anywhere dismisses it. When false (default), the
   *  ring fades after OVERLAY_DURATION_MS like clicky's behavior. */
  persistPointer: boolean;

  setCompanionEnabled: (v: boolean) => void;
  setPttKey: (key: CompanionPttKey) => void;
  setTtsVoiceId: (id: string) => void;
  setPersistPointer: (v: boolean) => void;
}

export const useCompanionSettingsStore = create<CompanionSettingsState>()(
  persist(
    (set) => ({
      companionEnabled: true,
      pttKey: "Right Shift",
      ttsVoiceId: "",
      persistPointer: false,

      setCompanionEnabled: (v) => set({ companionEnabled: v }),
      setPttKey: (key) => set({ pttKey: key }),
      setTtsVoiceId: (id) => set({ ttsVoiceId: id }),
      setPersistPointer: (v) => set({ persistPointer: v }),
    }),
    {
      name: "companion-settings",
      storage: tauriStorage,
    },
  ),
);
