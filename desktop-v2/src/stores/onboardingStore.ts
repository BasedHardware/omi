import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { LazyStore } from "@tauri-apps/plugin-store";
import { invoke } from "@tauri-apps/api/core";

const tauriStore = new LazyStore("onboarding.json");

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

export const ONBOARDING_STEP_IDS = [
  "name",
  "language",
  "trust",
  "screen_recording",
  "full_disk_access",
  "file_scan",
  "microphone",
  "notifications",
  "accessibility",
  "automation",
  "floating_bar_shortcut",
  "floating_bar_demo",
  "voice_shortcut",
  "voice_demo",
  "research",
  "goal",
  "tasks",
] as const;

export type OnboardingStepId = (typeof ONBOARDING_STEP_IDS)[number];

export type PermissionStatus = "granted" | "waiting" | "not_granted";

interface OnboardingState {
  hasCompletedOnboarding: boolean;
  currentStepIndex: number;
  preferredName: string;
  language: string | null;
  goal: string | null;
  floatingBarShortcut: string;
  voiceShortcut: string;
  permissions: Record<string, PermissionStatus>;

  setPreferredName: (name: string) => void;
  setLanguage: (lang: string | null) => void;
  setGoal: (goal: string | null) => void;
  setFloatingBarShortcut: (shortcut: string) => void;
  setVoiceShortcut: (shortcut: string) => void;
  setPermission: (kind: string, status: PermissionStatus) => void;
  advance: () => void;
  skip: () => void;
  goBack: () => void;
  setStepIndex: (i: number) => void;
  markCompleted: () => Promise<void>;
  resetOnboarding: () => void;
}

const persistedKeys: Array<keyof OnboardingState> = [
  "hasCompletedOnboarding",
  "preferredName",
  "language",
  "goal",
  "floatingBarShortcut",
  "voiceShortcut",
];

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      hasCompletedOnboarding: false,
      currentStepIndex: 0,
      preferredName: "",
      language: null,
      goal: null,
      floatingBarShortcut: "Cmd+Shift+Space",
      voiceShortcut: "Option",
      permissions: {},

      setPreferredName: (name) => set({ preferredName: name }),
      setLanguage: (lang) => set({ language: lang }),
      setGoal: (goal) => set({ goal }),
      setFloatingBarShortcut: (s) => set({ floatingBarShortcut: s }),
      setVoiceShortcut: (s) => set({ voiceShortcut: s }),
      setPermission: (kind, status) =>
        set((state) => ({
          permissions: { ...state.permissions, [kind]: status },
        })),
      advance: () =>
        set((state) => ({ currentStepIndex: state.currentStepIndex + 1 })),
      skip: () =>
        set((state) => ({ currentStepIndex: state.currentStepIndex + 1 })),
      goBack: () =>
        set((state) => ({
          currentStepIndex: Math.max(0, state.currentStepIndex - 1),
        })),
      setStepIndex: (i) => set({ currentStepIndex: Math.max(0, i) }),
      markCompleted: async () => {
        set({ hasCompletedOnboarding: true });
        try {
          await invoke("set_onboarding_completed", { completed: true });
        } catch (err) {
          console.warn("[onboarding] backend sync failed:", err);
        }
      },
      resetOnboarding: () =>
        set({
          hasCompletedOnboarding: false,
          currentStepIndex: 0,
          preferredName: "",
          language: null,
          goal: null,
          permissions: {},
        }),
    }),
    {
      name: "onboarding-state",
      storage: tauriStorage,
      partialize: (state) =>
        Object.fromEntries(
          persistedKeys.map((k) => [k, state[k]]),
        ) as Partial<OnboardingState>,
    },
  ),
);

// Dev helper: `window.__resetOnboarding()` from the browser console restarts
// the flow without needing to navigate to Settings. Safe to ship — it only
// clears local onboarding state, never affects the backend or auth.
if (typeof window !== "undefined") {
  (window as unknown as { __resetOnboarding?: () => void }).__resetOnboarding =
    () => {
      useOnboardingStore.getState().resetOnboarding();
      console.info(
        "[onboarding] reset — reload or navigate to trigger the flow again",
      );
    };
}

