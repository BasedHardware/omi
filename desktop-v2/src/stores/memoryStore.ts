import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";

export interface Memory {
  id: string;
  content: string;
  category?: string;
  created_at: string;
  updated_at?: string;
  structured?: {
    title?: string;
    emoji?: string;
    category?: string;
  };
}

interface MemoryState {
  memories: Memory[];
  isLoading: boolean;
  query: string;
  categoryFilter: string | null;
  loadMemories: () => Promise<void>;
  deleteMemory: (id: string) => Promise<void>;
  setQuery: (q: string) => void;
  setCategoryFilter: (c: string | null) => void;
  filteredMemories: () => Memory[];
}

export const useMemoryStore = create<MemoryState>((set, get) => ({
  memories: [],
  isLoading: false,
  query: "",
  categoryFilter: null,

  setQuery: (q: string) => set({ query: q }),

  setCategoryFilter: (c: string | null) => set({ categoryFilter: c }),

  filteredMemories: () => {
    const { memories, query, categoryFilter } = get();
    const normalizedQuery = query.trim().toLowerCase();
    return memories.filter((memory) => {
      if (normalizedQuery.length > 0) {
        const content = memory.content?.toLowerCase() ?? "";
        const title = memory.structured?.title?.toLowerCase() ?? "";
        if (
          !content.includes(normalizedQuery) &&
          !title.includes(normalizedQuery)
        ) {
          return false;
        }
      }
      if (categoryFilter !== null) {
        const category = memory.structured?.category ?? memory.category;
        if (category !== categoryFilter) {
          return false;
        }
      }
      return true;
    });
  },

  loadMemories: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });

    try {
      const data = await api.get<Memory[]>(
        "/v3/memories?limit=50&offset=0",
      );
      set({
        memories: Array.isArray(data) ? data : [],
        isLoading: false,
      });
    } catch (error) {
      console.error("Failed to load memories:", error);
      set({ isLoading: false });
    }
  },

  deleteMemory: async (id: string) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    // Optimistic removal
    const prev = get().memories;
    set({ memories: prev.filter((m) => m.id !== id) });

    try {
      await api.delete(`/v3/memories/${id}`);
    } catch (error) {
      console.error("Failed to delete memory:", error);
      set({ memories: prev });
    }
  },
}));
