import { create } from 'zustand';
import { DeepgramStream, TranscriptSegment } from '@/services/stt';
import { createVoiceprint, Voiceprint } from '@/services/voiceprint';
import { startMic, MicHandle } from '@/services/mic';
import { omiBle, sttCodecName, omiStreamParams, type OmiCodec } from '@/services/omiBle';
import { appendSegments } from '@/services/localConversations';
import { ENV } from '@/config/env';
import { useAuthStore } from '@/state/authStore';

/** Where the audio is coming from. Both end up in the same websocket. */
export type CaptureSource = 'mic' | 'omi';

interface CaptureState {
  /** Which source the current session is using, for the UI to report. */
  source: CaptureSource | null;
  recording: boolean;
  connecting: boolean;
  error: string | null;
  segments: TranscriptSegment[];
  voiceprint: Voiceprint;
  stream: DeepgramStream | null;
  start: () => void;
  /** Starts capture from the omi wearable instead of the phone mic. */
  startFromOmi: (codec: OmiCodec) => void;
  stop: () => void;
  pushSegment: (seg: TranscriptSegment) => void;
}

/**
 * Build an authorized STT websocket URL. We go through the Omi backend proxy
 * (`ENV.listenWsUrl`) with the short-lived user ID token rather than a bundled
 * provider key. React Native's WebSocket cannot set headers, so the token is
 * passed as a query parameter the backend accepts.
 */
export function authorizedStreamUrl(extra?: Record<string, string>): string | null {
  const token = useAuthStore.getState().token;
  if (!token) return null;
  try {
    const url = new URL(ENV.listenWsUrl);
    url.searchParams.set('token', token);
    // Flutter passes the codec, sample rate and channels as query parameters
    // (transcription_service.dart), not as a JSON control frame on the socket.
    // The mic path omits them because the proxy already knows its format.
    for (const [k, v] of Object.entries(extra ?? {})) url.searchParams.set(k, v);
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
  source: null,
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
          // Kept, not discarded: this is the only signal that separates "you" from
          // "everyone else" locally, and answering "what did marco say" depends on
          // it. `void isUser` used to sit here, throwing the verdict away.
          get().pushSegment({ ...seg, speaker: label, isUser });
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
  startFromOmi: (codec) => {
    const { recording, connecting, stream } = get();
    if (recording || connecting || stream) return;

    if (!sttCodecName(codec)) {
      set({ error: `Device codec ${codec} is not supported by the STT backend.` });
      return;
    }

    const params = omiStreamParams(codec);
    const url = params ? authorizedStreamUrl(params) : null;
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
          get().pushSegment({ ...seg, speaker: label, isUser });
        },
        onOpen: () => {
          set({ connecting: false, recording: true, error: null, source: 'omi' });
          // Device bytes are forwarded exactly as they arrive. No decode: the
          // backend is told the codec and sample rate in the query string, which
          // is what Flutter does, so decoding opus here would be work thrown away.
          void omiBle.startAudio().then((ok) => {
            if (!ok) {
              get().stop();
              set({ error: `Could not enable device audio: ${omiBle.startAudioError() ?? 'unknown'}` });
              return;
            }
            omiBle.onAudio(
              (bytes) => get().stream?.sendAudio(bytes.buffer as ArrayBuffer),
              (e) => {
                console.error('[capture] omi audio error:', e);
                get().stop();
                set({ error: 'Device audio stream failed.' });
              },
            );
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
    const { segments, source } = get();
    teardownMic();
    // Unsubscribe before closing the socket: leaving the notification enabled
    // after a stop means the device keeps pushing audio into a dead stream.
    omiBle.stopAudio();
    get().stream?.close();
    set({ recording: false, connecting: false, stream: null, source: null });

    // Persist before clearing, so a stop still leaves the words behind. This is
    // what makes the assistant work with no account: there is nothing on the
    // server to fall back on, so on-device storage is the record.
    const saved = segments.filter((x) => x.isFinal && x.text.trim());
    if (saved.length > 0) {
      void appendSegments(
        saved.map((x) => ({ text: x.text, speaker: x.speaker, isUser: x.isUser, start: x.start })),
        source ?? 'mic'
      ).catch((e) => console.warn('[capture] could not save locally:', e));
    }
    set({ segments: [], voiceprint: createVoiceprint() });
  },
  pushSegment: (seg) => set({ segments: [...get().segments, seg] }),
  /** Writes this session's segments to on-device storage. Called on stop(). */
}));
