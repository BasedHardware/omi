/**
 * Audio store — controls the `audio-capture` plugin and exposes recording
 * state to the UI.
 *
 * Like the Rewind store, audio capture is gated by "commercial time" (default
 * Mon-Fri 9am-5pm). When the user toggles audio on, we store that preference;
 * actual capture only runs during commercial hours and auto-resumes when the
 * window re-opens.
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useDevStore } from "./devStore";
import {
  startRecording,
  stopRecording,
  getCaptureState,
  type CaptureState,
  type VadMode,
} from "@/services/audioCapture";
import { isCommercialTime, watchCommercialTime } from "@/utils/commercialTime";
import { useConversationStore } from "./conversationStore";

export type { VadMode } from "@/services/audioCapture";

export interface LiveSegment {
  text: string;
  speaker: string;
  speakerId: number;
  isUser: boolean;
  start: number;
  end: number;
}

export interface TranscriptionLanguage {
  code: string;
  label: string;
}

export const TRANSCRIPTION_LANGUAGES: TranscriptionLanguage[] = [
  { code: "pt-BR", label: "Português (Brasil)" },
  { code: "en", label: "English" },
];

const LANGUAGE_STORAGE_KEY = "nooto.audio.language";
const VAD_MODE_STORAGE_KEY = "nooto.audio.vadMode";
const LEGACY_VAD_ENABLED_STORAGE_KEY = "nooto.audio.vadEnabled";

const VAD_MODES: readonly VadMode[] = ["off", "sensitive", "balanced", "aggressive"];

function isVadMode(v: string | null): v is VadMode {
  return !!v && (VAD_MODES as readonly string[]).includes(v);
}

function readStoredLanguage(): string {
  if (typeof window === "undefined") return "pt-BR";
  try {
    const v = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (v && TRANSCRIPTION_LANGUAGES.some((l) => l.code === v)) return v;
  } catch {
    // ignore
  }
  return "pt-BR";
}

function readStoredVadMode(): VadMode {
  if (typeof window === "undefined") return "off";
  try {
    const v = window.localStorage.getItem(VAD_MODE_STORAGE_KEY);
    if (isVadMode(v)) return v;

    const legacy = window.localStorage.getItem(LEGACY_VAD_ENABLED_STORAGE_KEY);
    if (legacy !== null) {
      const migrated: VadMode = legacy === "1" ? "aggressive" : "off";
      try {
        window.localStorage.setItem(VAD_MODE_STORAGE_KEY, migrated);
        window.localStorage.removeItem(LEGACY_VAD_ENABLED_STORAGE_KEY);
      } catch {
        // ignore
      }
      return migrated;
    }
  } catch {
    // ignore
  }
  return "off";
}

interface AudioState {
  audioEnabled: boolean;
  isRecording: boolean;
  deviceName: string | null;
  sampleRate: number;
  inCommercialHours: boolean;
  recordingStartedAt: number | null;
  liveTranscript: string;
  liveSegments: LiveSegment[];
  livePartialBySpeaker: Record<string, string>;
  isProcessing: boolean;
  processingError: string | null;
  language: string;
  vadMode: VadMode;

  toggleAudio: () => Promise<void>;
  startAudio: () => Promise<void>;
  stopAudio: () => Promise<void>;
  refreshState: () => Promise<void>;
  setLanguage: (code: string) => Promise<void>;
  setVadMode: (mode: VadMode) => Promise<void>;
  dismissProcessingError: () => void;
}

function applyCaptureState(
  set: (p: Partial<AudioState>) => void,
  get: () => AudioState,
  state: CaptureState,
): void {
  const wasRecording = get().isRecording;
  set({
    isRecording: state.is_capturing,
    deviceName: state.device_name,
    sampleRate: state.sample_rate,
    recordingStartedAt: state.is_capturing
      ? wasRecording
        ? get().recordingStartedAt
        : Date.now()
      : null,
  });
}

export const useAudioStore = create<AudioState>((set, get) => ({
  audioEnabled: false,
  isRecording: false,
  deviceName: null,
  sampleRate: 16000,
  inCommercialHours: isCommercialTime(),
  recordingStartedAt: null,
  liveTranscript: "",
  liveSegments: [],
  livePartialBySpeaker: {},
  isProcessing: false,
  processingError: null,
  language: readStoredLanguage(),
  vadMode: readStoredVadMode(),

  toggleAudio: async () => {
    const { audioEnabled } = get();
    if (audioEnabled) {
      await get().stopAudio();
      set({ audioEnabled: false });
    } else {
      set({ audioEnabled: true });
      await get().startAudio();
    }
  },

  startAudio: async () => {
    if (!get().inCommercialHours) {
      return;
    }
    if (get().isRecording) return;
    try {
      set({
        liveTranscript: "",
        liveSegments: [],
        livePartialBySpeaker: {},
        processingError: null,
      });
      const state = await startRecording({
        sample_rate: 16000,
        channels: 1,
        language: get().language,
        vad_mode: get().vadMode,
      });
      applyCaptureState(set, get, state);
    } catch (err) {
      console.error("[Audio] startRecording failed:", err);
    }
  },

  stopAudio: async () => {
    if (!get().isRecording) return;
    try {
      const state = await stopRecording();
      applyCaptureState(set, get, state);
      set({
        liveTranscript: "",
        liveSegments: [],
        livePartialBySpeaker: {},
        processingError: null,
      });
      void useConversationStore.getState().loadConversations();
    } catch (err) {
      console.error("[Audio] stopRecording failed:", err);
      set({
        isProcessing: false,
        processingError: `Couldn't stop recording: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  },

  dismissProcessingError: () => set({ processingError: null }),

  refreshState: async () => {
    try {
      const state = await getCaptureState();
      applyCaptureState(set, get, state);
    } catch (err) {
      console.error("[Audio] getCaptureState failed:", err);
    }
  },

  setLanguage: async (code: string) => {
    if (!TRANSCRIPTION_LANGUAGES.some((l) => l.code === code)) return;
    if (get().language === code) return;
    set({ language: code });
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    } catch {
      // ignore
    }
    if (get().isRecording) {
      await get().stopAudio();
      await get().startAudio();
    }
  },

  setVadMode: async (mode: VadMode) => {
    if (get().vadMode === mode) return;
    set({ vadMode: mode });
    try {
      window.localStorage.setItem(VAD_MODE_STORAGE_KEY, mode);
    } catch {
      // ignore
    }
    if (get().isRecording) {
      await get().stopAudio();
      await get().startAudio();
    }
  },
}));

// ---------------------------------------------------------------------------
// Live transcript event subscription
// ---------------------------------------------------------------------------

interface TranscriptEvent {
  text: string;
  is_final: boolean;
  speaker: string;
  speaker_id: number;
  is_user: boolean;
  start: number;
  end: number;
}

listen<TranscriptEvent>("transcript:partial", (event) => {
  const { text, is_final, speaker, speaker_id, is_user, start, end } = event.payload;
  if (!text) return;

  // Forward the segment into the shared Rust buffer so the live-transcript
  // floating window can drain it via polling. WebKitGTK won't reliably
  // deliver `app.emit` to freshly-mounted auxiliary windows, so we can't
  // rely on the same event there.
  void invoke("push_live_transcript_segment", {
    segment: {
      text,
      isFinal: is_final,
      speaker: speaker ?? "",
      speakerId: speaker_id ?? 0,
      isUser: is_user ?? false,
      start: start ?? 0,
      end: end ?? 0,
    },
  }).catch(() => {
    // Command may not exist in older builds — non-fatal.
  });

  useAudioStore.setState((prev) => {
    const nextPartial = { ...prev.livePartialBySpeaker };
    if (is_final) {
      delete nextPartial[speaker];
      return {
        liveTranscript: text,
        livePartialBySpeaker: nextPartial,
        liveSegments: [
          ...prev.liveSegments,
          {
            text,
            speaker,
            speakerId: speaker_id,
            isUser: is_user,
            start,
            end,
          },
        ],
      };
    }
    nextPartial[speaker] = text;
    return {
      liveTranscript: text,
      livePartialBySpeaker: nextPartial,
    };
  });
})
  .then(() => console.log("[Audio] subscribed to transcript:partial"))
  .catch((err) => {
    console.error("[Audio] failed to subscribe to transcript:partial:", err);
  });

// ---------------------------------------------------------------------------
// Live-transcript floating window — show/hide driven by isRecording.
//
// Zustand's `subscribe` fires on every state change. We latch the previous
// value so we only call the Tauri command on the boolean transition, not on
// every downstream update (new partials, elapsed tick, etc).
// ---------------------------------------------------------------------------

let prevIsRecording = useAudioStore.getState().isRecording;
useAudioStore.subscribe((state) => {
  if (state.isRecording === prevIsRecording) return;
  prevIsRecording = state.isRecording;
  // The floating live-transcript window is gated behind a developer-mode
  // toggle — off by default so normal users don't get a surprise overlay.
  // Always clear the buffer on new-meeting start so when the user later
  // enables the flag, they don't see stale segments.
  const enabled = useDevStore.getState().liveTranscriptWindowEnabled;
  if (state.isRecording) {
    void invoke("clear_live_transcript_buffer").catch(() => {});
    if (enabled) {
      void invoke("show_live_transcript").catch((err) =>
        console.warn("[Audio] show_live_transcript failed:", err),
      );
    }
  } else {
    // Always try to hide — cheap no-op if already hidden, and covers the
    // case where the user flipped the flag off mid-meeting.
    void invoke("hide_live_transcript").catch((err) =>
      console.warn("[Audio] hide_live_transcript failed:", err),
    );
  }
});

// React to dev-mode toggle changes WHILE a meeting is already in progress.
// Flipping the flag on should open the window immediately; flipping off
// should hide it without stopping the recording.
let prevLtEnabled = useDevStore.getState().liveTranscriptWindowEnabled;
useDevStore.subscribe((state) => {
  if (state.liveTranscriptWindowEnabled === prevLtEnabled) return;
  prevLtEnabled = state.liveTranscriptWindowEnabled;
  const isRecording = useAudioStore.getState().isRecording;
  if (!isRecording) return;
  if (state.liveTranscriptWindowEnabled) {
    void invoke("show_live_transcript").catch(() => {});
  } else {
    void invoke("hide_live_transcript").catch(() => {});
  }
});

// ---------------------------------------------------------------------------
// Commercial-time watcher
// ---------------------------------------------------------------------------

watchCommercialTime(async (isOpen) => {
  const { audioEnabled, isRecording, startAudio, stopAudio } =
    useAudioStore.getState();
  useAudioStore.setState({ inCommercialHours: isOpen });

  if (isOpen) {
    if (audioEnabled && !isRecording) {
      await startAudio();
    }
  } else {
    if (isRecording) {
      await stopAudio();
    }
  }
});
