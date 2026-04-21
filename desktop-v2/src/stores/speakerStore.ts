/**
 * Speaker store — maps speaker IDs to human-readable names.
 *
 * Names are persisted to localStorage so the mapping survives across
 * reloads and across new live recordings (speaker IDs are per-session,
 * so this is a best-effort display hint — we still honour the authoritative
 * person IDs once a meeting is saved to the backend).
 *
 * Mirrors the Swift `SpeakerNameMap` backing `LiveNameSpeakerSheet`:
 * when the user identifies "Speaker 2" during a live meeting, we store the
 * mapping under that speaker label (e.g. `SPEAKER_2 → "Alex"`) and reapply
 * it across the whole transcript view.
 */

import { create } from "zustand";

const STORAGE_KEY = "nooto.speakers.names";

interface StoredShape {
  /** speaker label (e.g. `SPEAKER_0`, `SPEAKER_1`) → human name */
  names: Record<string, string>;
}

function readStored(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as StoredShape;
    if (parsed && typeof parsed.names === "object" && parsed.names) {
      return { ...parsed.names };
    }
  } catch {
    // corrupt — start fresh
  }
  return {};
}

function persist(names: Record<string, string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ names }));
  } catch {
    // ignore
  }
}

interface SpeakerState {
  names: Record<string, string>;
  /** Set a friendly name for a speaker label. Empty/whitespace names clear the mapping. */
  setName: (speaker: string, name: string) => void;
  /** Remove a previously set name. */
  clearName: (speaker: string) => void;
  /** Clear all speaker name mappings (used when a meeting is saved/reset). */
  clearAll: () => void;
  /** Convenience lookup. */
  getName: (speaker: string) => string | undefined;
}

export const useSpeakerStore = create<SpeakerState>((set, get) => ({
  names: readStored(),

  setName: (speaker: string, name: string) => {
    const trimmed = name.trim();
    set((prev) => {
      const next = { ...prev.names };
      if (!trimmed) {
        delete next[speaker];
      } else {
        next[speaker] = trimmed;
      }
      persist(next);
      return { names: next };
    });
  },

  clearName: (speaker: string) => {
    set((prev) => {
      if (!(speaker in prev.names)) return prev;
      const next = { ...prev.names };
      delete next[speaker];
      persist(next);
      return { names: next };
    });
  },

  clearAll: () => {
    persist({});
    set({ names: {} });
  },

  getName: (speaker: string) => get().names[speaker],
}));

/**
 * Format the final display label for a speaker:
 * - user → "You"
 * - named speaker → the stored name
 * - otherwise → "Speaker <N>"
 */
export function formatSpeakerDisplayName(
  speaker: string | null | undefined,
  isUser: boolean,
  names: Record<string, string>,
): string {
  if (isUser) return "You";
  if (!speaker) return "Speaker";
  const stored = names[speaker];
  if (stored) return stored;
  // Turn "SPEAKER_2" into "Speaker 2"
  const cleaned = speaker.replace(/_/g, " ");
  return cleaned
    .split(" ")
    .map((p) => (p.length > 0 ? p[0].toUpperCase() + p.slice(1).toLowerCase() : p))
    .join(" ");
}
