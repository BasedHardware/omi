import { create } from 'zustand';
import { listConversations, getConversation, Conversation } from '@/api/omiApi';

interface ConversationsState {
  items: Conversation[];
  loading: boolean;
  error: string | null;
  selected: Conversation | null;
  load: () => Promise<void>;
  open: (id: string) => Promise<void>;
}

export const useConversationsStore = create<ConversationsState>((set, get) => ({
  items: [],
  loading: false,
  error: null,
  selected: null,
  load: async () => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const items = await listConversations(50, 0);
      set({ items });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load conversations';
      console.error('[conversations] load failed:', msg);
      set({ error: msg });
    } finally {
      set({ loading: false });
    }
  },
  open: async (id) => {
    try {
      const selected = await getConversation(id);
      set({ selected, error: null });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load conversation';
      console.error('[conversations] open failed:', msg);
      set({ error: msg });
    }
  },
}));
