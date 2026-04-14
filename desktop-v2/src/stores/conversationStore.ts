import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";

export interface ActionItem {
  description: string;
  completed: boolean;
}

export interface Conversation {
  id: string;
  structured: {
    title: string;
    overview: string;
    emoji?: string;
    category?: string;
    action_items?: ActionItem[];
  };
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
  transcript_segments?: TranscriptSegment[];
  starred?: boolean;
}

export interface TranscriptSegment {
  text: string;
  speaker: string;
  start: number;
  end: number;
}

interface ConversationState {
  conversations: Conversation[];
  isLoading: boolean;
  selectedConversation: Conversation | null;
  isLoadingDetail: boolean;
  searchQuery: string;
  loadConversations: () => Promise<void>;
  searchConversations: (query: string) => void;
  selectConversation: (conversation: Conversation | null) => void;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  isLoading: false,
  selectedConversation: null,
  isLoadingDetail: false,
  searchQuery: "",

  loadConversations: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });

    try {
      const data = await api.get<Conversation[]>(
        "/v1/conversations?limit=50&offset=0&statuses=completed&include_discarded=false",
      );
      set({
        conversations: Array.isArray(data) ? data : [],
        isLoading: false,
      });
    } catch (error) {
      console.error("Failed to load conversations:", error);
      set({ isLoading: false });
    }
  },

  searchConversations: (query: string) => {
    set({ searchQuery: query });
    if (!query.trim()) {
      get().loadConversations();
    }
  },

  selectConversation: async (conversation: Conversation | null) => {
    if (!conversation) {
      set({ selectedConversation: null });
      return;
    }

    // Show the conversation from the list immediately
    set({ selectedConversation: conversation, isLoadingDetail: true });

    // Fetch full detail (includes transcript_segments)
    try {
      const detail = await api.get<Conversation>(
        `/v1/conversations/${conversation.id}`,
      );
      set({ selectedConversation: detail, isLoadingDetail: false });
    } catch (error) {
      console.error("Failed to load conversation detail:", error);
      set({ isLoadingDetail: false });
    }
  },
}));
