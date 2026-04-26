import { create } from "zustand";
import type { CaptureDisplayMeta } from "@/services/coordinateMap";
import type { ScreenshotWithOcr } from "@/services/rewind";

export type CompanionState = "idle" | "listening" | "thinking" | "speaking";

export interface CompanionPoint {
  x: number;
  y: number;
  label?: string;
}

/** Capture snapshot taken at `companion:start` time (before the user releases PTT). */
export interface CompanionCapture {
  capture: ScreenshotWithOcr & { display_meta?: CaptureDisplayMeta };
  display_meta: CaptureDisplayMeta | null;
}

/** Character range within `answer` that the TTS engine is currently speaking. */
export interface SpeakingRange {
  start: number;
  end: number;
}

/** A guided multi-step chain in progress. Lives only in memory while running.
 *  Each step's coordinates are re-grounded just-in-time as the user advances,
 *  so we only persist the text plan here, not the per-step pixel positions. */
export interface CompanionChainStep {
  instruction: string;
  target_label: string;
}
export interface CompanionChain {
  steps: CompanionChainStep[];
  /** 0-based index into `steps`. Equal to `steps.length` when finished. */
  currentIndex: number;
}

interface CompanionStore {
  enabled: boolean;
  state: CompanionState;
  /** Overlay-local points returned by Gemini, already mapped to CSS pt space. */
  points: CompanionPoint[];
  /** Display ID that the points belong to (matches the overlay window suffix). */
  activeDisplayId: number | null;
  /** Gemini's text answer for the current session. */
  answer: string | null;
  /** Error message from the most recent failed session. */
  errorMessage: string | null;
  /** The capture taken at PTT-start time. */
  sessionCapture: CompanionCapture | null;
  /** Monotonically incrementing ID — used to discard stale in-flight responses. */
  requestId: number;
  /**
   * Opaque ID returned by `tts_speak` and echoed back by `tts:willSpeakRange`.
   * Used to discard range events from a previous (interrupted) utterance.
   */
  currentTtsId: string | null;
  /**
   * Character range within `answer` that AVSpeechSynthesizer is currently
   * vocalising. Null when nothing is highlighted (before first word or after
   * TTS completes / is cancelled).
   */
  speakingRange: SpeakingRange | null;
  /** In-flight guided chain, or null when no chain is running. */
  chain: CompanionChain | null;

  setEnabled: (enabled: boolean) => void;
  setState: (state: CompanionState) => void;
  setPoints: (points: CompanionPoint[], displayId: number | null) => void;
  setAnswer: (answer: string | null) => void;
  setErrorMessage: (msg: string | null) => void;
  setSessionCapture: (capture: CompanionCapture | null) => void;
  /** Increments requestId and returns the new value. */
  nextRequestId: () => number;
  setCurrentTtsId: (id: string | null) => void;
  setSpeakingRange: (range: SpeakingRange | null) => void;
  setChain: (chain: CompanionChain | null) => void;
  /** Increment the current step. Returns the new index, or null if the chain
   *  was already at its final step (caller should clear the chain). */
  advanceChain: () => number | null;
  resetSession: () => void;
}

export const useCompanionStore = create<CompanionStore>()((set, get) => ({
  enabled: false,
  state: "idle",
  points: [],
  activeDisplayId: null,
  answer: null,
  errorMessage: null,
  sessionCapture: null,
  requestId: 0,
  currentTtsId: null,
  speakingRange: null,
  chain: null,

  setEnabled: (enabled) => set({ enabled }),
  setState: (state) => set({ state }),
  setPoints: (points, displayId) => set({ points, activeDisplayId: displayId }),
  setAnswer: (answer) => set({ answer }),
  setErrorMessage: (errorMessage) => set({ errorMessage }),
  setSessionCapture: (sessionCapture) => set({ sessionCapture }),
  nextRequestId: () => {
    const next = get().requestId + 1;
    set({ requestId: next });
    return next;
  },
  setCurrentTtsId: (currentTtsId) => set({ currentTtsId }),
  setSpeakingRange: (speakingRange) => set({ speakingRange }),
  setChain: (chain) => set({ chain }),
  advanceChain: () => {
    const c = get().chain;
    if (!c) return null;
    const next = c.currentIndex + 1;
    if (next >= c.steps.length) return null;
    set({ chain: { ...c, currentIndex: next } });
    return next;
  },
  resetSession: () =>
    set({
      points: [],
      activeDisplayId: null,
      answer: null,
      errorMessage: null,
      sessionCapture: null,
      currentTtsId: null,
      speakingRange: null,
      chain: null,
    }),
}));
