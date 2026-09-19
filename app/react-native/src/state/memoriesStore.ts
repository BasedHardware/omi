import { create } from 'zustand';
import { getMemories, createMemory, Memory } from '@/api/omiApi';

interface MemoriesState {
  items: Memory[];
  loading: boolean;
  error: string | null;
  load: (refresh?: boolean) => Promise<void>;
  add: (content: string, tags?: string[]) => Promise<void>;
}

export const useMemoriesStore = create<MemoriesState>((set, get) => ({
  items: [],
  loading: false,
  error: null,
  load: async (_refresh = false) => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      // /v3/memories returns a bare array; page by limit/offset until a short page.
      const all: Memory[] = [];
      let offset = 0;
      const limit = 200;
      for (;;) {
        const page = await getMemories(limit, offset);
        all.push(...page);
        if (page.length < limit) break;
        offset += limit;
      }
      set({ items: all });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load memories';
      console.error('[memories] load failed:', msg);
      set({ error: msg });
    } finally {
      set({ loading: false });
    }
  },
  add: async (content, tags = []) => {
    const memory = await createMemory(content, tags);
    set({ items: [memory, ...get().items] });
  },
}));
