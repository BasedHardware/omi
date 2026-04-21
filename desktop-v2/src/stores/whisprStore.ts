import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { nanoid } from "nanoid";

export interface WhisprEntry {
  id: string;
  text: string;
  /** ISO timestamp. */
  createdAt: string;
  /** Milliseconds the PTT key was held. */
  durationMs?: number;
  /** Whether the auto-paste keystroke was attempted. */
  autoPasted?: boolean;
}

interface WhisprState {
  entries: WhisprEntry[];
  /** Add a new transcript to history. Returns the created entry. */
  record: (
    input: Omit<WhisprEntry, "id" | "createdAt"> &
      Partial<Pick<WhisprEntry, "createdAt">>,
  ) => WhisprEntry;
  remove: (id: string) => void;
  clear: () => void;
}

const MAX_ENTRIES = 500;

export const useWhisprStore = create<WhisprState>()(
  persist(
    (set) => ({
      entries: [],
      record: (input) => {
        const entry: WhisprEntry = {
          id: nanoid(),
          createdAt: input.createdAt ?? new Date().toISOString(),
          text: input.text,
          durationMs: input.durationMs,
          autoPasted: input.autoPasted,
        };
        set((state) => ({
          entries: [entry, ...state.entries].slice(0, MAX_ENTRIES),
        }));
        return entry;
      },
      remove: (id) =>
        set((state) => ({ entries: state.entries.filter((e) => e.id !== id) })),
      clear: () => set({ entries: [] }),
    }),
    {
      name: "nooto.whispr.history.v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ entries: state.entries }),
    },
  ),
);
