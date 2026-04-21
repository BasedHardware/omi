import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { useConversationStore } from "./conversationStore";
import { api } from "../services/api";
import type { OmiApp } from "../types/app";

interface AppState {
  apps: OmiApp[];
  isLoading: boolean;
  isReprocessing: boolean;
  reprocessingAppId: string | null;
  searchQuery: string;
  selectedCapability: string | null;
  loadApps: () => Promise<void>;
  setSearchQuery: (q: string) => void;
  setSelectedCapability: (c: string | null) => void;
  enableApp: (id: string) => Promise<void>;
  disableApp: (id: string) => Promise<void>;
  reprocessConversation: (conversationId: string, appId: string) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  apps: [],
  isLoading: false,
  isReprocessing: false,
  reprocessingAppId: null,
  searchQuery: "",
  selectedCapability: null,

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
}));
