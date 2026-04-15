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
import { listen } from "@tauri-apps/api/event";
import {
  startRecording,
  stopRecording,
  getCaptureState,
  type CaptureState,
} from "@/services/audioCapture";
import { isCommercialTime, watchCommercialTime } from "@/utils/commercialTime";

interface AudioState {
  /** True when the user has audio recording enabled (may still be paused outside commercial hours). */
  audioEnabled: boolean;
  /** True when the Rust side is actively capturing audio right now. */
  isRecording: boolean;
  /** Current active device name (from Rust). */
  deviceName: string | null;
  /** Target sample rate (from Rust). */
  sampleRate: number;
  /** True when we're within the commercial-time window. */
  inCommercialHours: boolean;
  /** Timestamp (ms) of when the current recording started. null when not recording. */
  recordingStartedAt: number | null;
  /** Live transcript text (interim or last final). Empty when nothing has been said yet. */
  liveTranscript: string;

  toggleAudio: () => Promise<void>;
  startAudio: () => Promise<void>;
  stopAudio: () => Promise<void>;
  refreshState: () => Promise<void>;
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
      // Defer — commercial-time watcher will start us when hours open.
      return;
    }
    if (get().isRecording) return;
    try {
      set({ liveTranscript: "" });
      const state = await startRecording();
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
      set({ liveTranscript: "" });
    } catch (err) {
      console.error("[Audio] stopRecording failed:", err);
    }
  },

  refreshState: async () => {
    try {
      const state = await getCaptureState();
      applyCaptureState(set, get, state);
    } catch (err) {
      console.error("[Audio] getCaptureState failed:", err);
    }
  },
}));

// ---------------------------------------------------------------------------
// Live transcript event subscription
// ---------------------------------------------------------------------------

interface TranscriptEvent {
  text: string;
  is_final: boolean;
}

listen<TranscriptEvent>("transcript:partial", (event) => {
  const { text, is_final } = event.payload;
  console.log("[Audio] transcript event:", { text, is_final });
  if (text) {
    useAudioStore.setState({ liveTranscript: text });
  }
})
  .then(() => console.log("[Audio] subscribed to transcript:partial"))
  .catch((err) => {
    console.error("[Audio] failed to subscribe to transcript:partial:", err);
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
