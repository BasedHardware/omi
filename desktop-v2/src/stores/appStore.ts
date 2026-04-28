import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { listen } from "@tauri-apps/api/event";
import { useAuthStore } from "./authStore";
import { useConversationStore } from "./conversationStore";
import { api, ApiError } from "../services/api";
import type { OmiApp } from "../types/app";

interface AppState {
  apps: OmiApp[];
  isLoading: boolean;
  isReprocessing: boolean;
  reprocessingAppId: string | null;
  searchQuery: string;
  selectedCapability: string | null;
  /** Per-app opt-in for writing back to the source tracker (e.g. mark a Jira
   *  ticket Done when the user completes it from the Plan view). Default is
   *  false everywhere — surprise writes are a trust hazard. */
  twoWaySyncByAppId: Record<string, boolean>;
  loadApps: () => Promise<void>;
  setSearchQuery: (q: string) => void;
  setSelectedCapability: (c: string | null) => void;
  enableApp: (id: string) => Promise<void>;
  disableApp: (id: string) => Promise<void>;
  setTwoWaySync: (appId: string, enabled: boolean) => void;
  reprocessConversation: (conversationId: string, appId: string) => Promise<void>;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
  apps: [],
  isLoading: false,
  isReprocessing: false,
  reprocessingAppId: null,
  searchQuery: "",
  selectedCapability: null,
  twoWaySyncByAppId: {},

  loadApps: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });

    try {
      // v1/apps returns a flat list with `enabled` and all metadata we need.
      // v2/apps groups by capability which is nice for marketplace UX, but we
      // can group client-side from the flat list and avoid an extra fetch.
      const data = await api.get<OmiApp[]>("/v1/apps?include_reviews=false");
      set({
        apps: Array.isArray(data) ? data : [],
        isLoading: false,
      });
    } catch (error) {
      console.error("[appStore] Failed to load apps:", error);
      set({ isLoading: false });
    }
  },

  setSearchQuery: (q: string) => set({ searchQuery: q }),
  setSelectedCapability: (c: string | null) => set({ selectedCapability: c }),

  enableApp: async (id: string) => {
    const prev = get().apps;
    set({
      apps: prev.map((a) => (a.id === id ? { ...a, enabled: true } : a)),
    });
    try {
      await api.post(`/v1/apps/enable?app_id=${encodeURIComponent(id)}`, {});
    } catch (error) {
      // Plugins that require OAuth (Jira, Linear, ClickUp, …) reject /enable
      // with 400 + detail="App setup is not completed" until the user has
      // gone through the plugin's auth flow. Open `app_home_url` in the
      // browser; the plugin redirects back via `nooto://app-setup-complete`,
      // which `setupAppEventListener` below catches and retries enable.
      if (error instanceof ApiError && error.status === 400 && error.detail === "App setup is not completed") {
        const app = prev.find((a) => a.id === id);
        // `auth_steps[0].url` points at the plugin's OAuth start (e.g.
        // `/auth/jira`); `app_home_url` is the plugin's API origin used to
        // resolve chat-tool endpoints, which on its own usually 404s. Prefer
        // the auth step, fall back to home.
        const ext = app?.external_integration;
        const target = ext?.auth_steps?.[0]?.url ?? ext?.app_home_url;
        const uid = useAuthStore.getState().userId;
        if (target && uid) {
          const sep = target.includes("?") ? "&" : "?";
          const url = `${target}${sep}uid=${encodeURIComponent(uid)}`;
          try {
            await openShell(url);
            console.info("[appStore] opened OAuth setup:", url);
          } catch (openErr) {
            console.error("[appStore] failed to open setup URL:", openErr);
            set({ apps: prev });
          }
          return;
        }
        console.warn("[appStore] setup required but no auth URL for", id);
      }
      console.error("[appStore] enable failed:", error);
      set({ apps: prev });
    }
  },

  disableApp: async (id: string) => {
    const prev = get().apps;
    set({
      apps: prev.map((a) => (a.id === id ? { ...a, enabled: false } : a)),
    });
    try {
      await api.post(`/v1/apps/disable?app_id=${encodeURIComponent(id)}`, {});
    } catch (error) {
      console.error("[appStore] disable failed:", error);
      set({ apps: prev });
    }
  },

  setTwoWaySync: (appId: string, enabled: boolean) => {
    set((state) => ({
      twoWaySyncByAppId: { ...state.twoWaySyncByAppId, [appId]: enabled },
    }));
  },

  reprocessConversation: async (conversationId: string, appId: string) => {
    set({ isReprocessing: true, reprocessingAppId: appId });
    try {
      await api.post(
        `/v1/conversations/${conversationId}/reprocess?app_id=${encodeURIComponent(appId)}`,
        {},
      );
      // Refetch detail so apps_results updates. Mirrors Swift flow.
      const currentId = useConversationStore.getState().selectedConversation?.id;
      if (currentId === conversationId) {
        await useConversationStore.getState().refreshSelectedConversation();
      }
    } catch (error) {
      console.error("[appStore] reprocess failed:", error);
    } finally {
      set({ isReprocessing: false, reprocessingAppId: null });
    }
  },
    }),
    {
      name: "app-prefs",
      storage: createJSONStorage(() => localStorage),
      // Only persist user prefs — `apps` itself is refetched from the server
      // on every loadApps() call and shouldn't be cached across reloads.
      partialize: (state) => ({ twoWaySyncByAppId: state.twoWaySyncByAppId }),
    },
  ),
);

/** Selector helper: true only when the user has explicitly opted in for this
 *  app. Defaults to false. Used by `taskStore.toggleTask` to decide whether
 *  to dispatch a writeback to the source tracker. */
export function isTwoWaySyncEnabled(appId: string | undefined): boolean {
  if (!appId) return false;
  return Boolean(useAppStore.getState().twoWaySyncByAppId?.[appId]);
}

/** Wires the `nooto://app-setup-complete?app_id=…` deep-link callback (emitted
 *  from `src-tauri/src/main.rs`) to reload the apps list and retry enable on
 *  the just-authorized app. Idempotent: safe to call once at app startup. */
let setupListenerAttached = false;

export async function attachAppSetupListener(): Promise<void> {
  if (setupListenerAttached) return;
  setupListenerAttached = true;
  await listen<{ app_id: string; status: string }>("apps:setup-complete", async (event) => {
    const { app_id, status } = event.payload ?? { app_id: "", status: "" };
    console.info("[appStore] apps:setup-complete", app_id, status);
    if (status && status !== "success") return;
    const store = useAppStore.getState();
    await store.loadApps();
    if (app_id) await store.enableApp(app_id);
  });
}
