import { create } from 'zustand';
import { DeepgramStream, TranscriptSegment } from '@/services/stt';
import { createVoiceprint, Voiceprint } from '@/services/voiceprint';
import { startMic, MicHandle } from '@/services/mic';
import { ENV } from '@/config/env';
import { useAuthStore } from '@/state/authStore';

interface CaptureState {
  recording: boolean;
  connecting: boolean;
  error: string | null;
  segments: TranscriptSegment[];
  voiceprint: Voiceprint;
  stream: DeepgramStream | null;
  start: () => void;
  stop: () => void;
  pushSegment: (seg: TranscriptSegment) => void;
}

/**
 * Build an authorized STT websocket URL. We go through the Omi backend proxy
 * (`ENV.listenWsUrl`) with the short-lived user ID token rather than a bundled
 * provider key. React Native's WebSocket cannot set headers, so the token is
 * passed as a query parameter the backend accepts.
 */
function authorizedStreamUrl(): string | null {
  const token = useAuthStore.getState().token;
  if (!token) return null;
  try {
    const url = new URL(ENV.listenWsUrl);
    url.searchParams.set('token', token);
    return url.toString();
  } catch {
    return null;
  }
}

// Kept outside the store so the (non-serializable) recorder handle never
// triggers re-renders and can't be accidentally reset.
let micHandle: MicHandle | null = null;

function teardownMic() {
  micHandle?.stop();
  micHandle = null;
}

export const useCaptureStore = create<CaptureState>((set, get) => ({
  recording: false,
  connecting: false,
  error: null,
  segments: [],
  voiceprint: createVoiceprint(),
  stream: null,
  start: () => {
    const { recording, connecting, stream } = get();
    if (recording || connecting || stream) return;

    const url = authorizedStreamUrl();
    if (!url) {
      set({ error: 'Not signed in: STT requires an authorized session.' });
      return;
    }

    const vp = get().voiceprint;
    const next = new DeepgramStream(
      {
        onSegment: (seg) => {
          if (!vp.isEnrolled()) vp.enroll(seg.speaker);
          const { label, isUser } = vp.labelForSpeaker(seg.speaker);
          get().pushSegment({ ...seg, speaker: label });
          void isUser;
        },
        onOpen: () => {
          // Socket is live; only then start the mic and flip to recording.
          set({ connecting: false, recording: true, error: null });
          void startMic(
            (bytes) => get().stream?.sendAudio(bytes),
            (err) => {
              console.error('[capture] mic error:', err);
              get().stop();
              set({ error: 'Microphone unavailable or permission denied.' });
            },
          ).then((handle) => {
            if (!handle) {
              get().stop();
              return;
            }
            // If stop() ran while the mic was still coming up, tear it down now.
            if (!get().recording) teardownMic();
            else micHandle = handle;
          });
        },
        onError: (err) => {
          console.error('[capture] STT error:', err);
          get().stop();
          set({ error: 'Speech capture failed to start. Check your connection and session.' });
        },
        onClose: () => {
          if (get().recording) get().stop();
        },
      },
      url,
    );

    set({ connecting: true, error: null, stream: next });
    next.connect();
  },
  stop: () => {
    teardownMic();
    get().stream?.close();
    set({ recording: false, connecting: false, stream: null });
  },
  pushSegment: (seg) => set({ segments: [...get().segments, seg] }),
}));
