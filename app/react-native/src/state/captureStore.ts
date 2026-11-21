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
  /** Snapshot of the previous session's segments (kept after stop for UI). */
  lastSegments: TranscriptSegment[];
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
let captureSessionId = 0;

function isActiveSession(id: number): boolean {
  return id === captureSessionId && (useCaptureStore.getState().connecting || useCaptureStore.getState().recording);
}

function teardownMic() {
  micHandle?.stop();
  micHandle = null;
}

function persistAndReset(sessionId: number, opts?: { error?: string | null }) {
  if (sessionId !== captureSessionId) return;
  const { segments, source } = useCaptureStore.getState();
  teardownMic();
  omiBle.stopAudio();
  try {
    useCaptureStore.getState().stream?.close();
  } catch {
    // ignore
  }

  const saved = segments.filter((x) => x.isFinal && x.text.trim());
  if (saved.length > 0) {
    void appendSegments(
      saved.map((x) => ({ text: x.text, speaker: x.speaker, isUser: x.isUser, start: x.start })),
      source ?? 'mic'
    ).catch((e) => console.warn('[capture] could not save locally:', e));
  }

  useCaptureStore.setState({
    recording: false,
    connecting: false,
    stream: null,
    source: null,
    error: opts?.error ?? useCaptureStore.getState().error,
    lastSegments: segments,
    segments: [],
    voiceprint: createVoiceprint(),
  });
}

export const useCaptureStore = create<CaptureState>((set, get) => ({
  source: null,
  recording: false,
  connecting: false,
  error: null,
  segments: [],
  lastSegments: [],
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

    const sessionId = ++captureSessionId;
    const vp = get().voiceprint;
    const next = new DeepgramStream(
      {
        onSegment: (seg) => {
          if (sessionId !== captureSessionId) return;
          if (!vp.isEnrolled()) vp.enroll(seg.speaker);
          const { label, isUser } = vp.labelForSpeaker(seg.speaker);
          get().pushSegment({ ...seg, speaker: label, isUser });
        },
        onOpen: () => {
          if (sessionId !== captureSessionId || get().stream !== next) return;
          // Socket is live; only then start the mic and flip to recording.
          set({ connecting: false, recording: true, error: null, source: 'mic' });
          void startMic(
            (bytes) => {
              if (sessionId !== captureSessionId || get().stream !== next) return;
              next.sendAudio(bytes);
            },
            (err) => {
              if (sessionId !== captureSessionId) return;
              console.error('[capture] mic error:', err);
              persistAndReset(sessionId, { error: 'Microphone unavailable or permission denied.' });
            },
          ).then((handle) => {
            if (sessionId !== captureSessionId || get().stream !== next) {
              handle?.stop();
              return;
            }
            if (!handle) {
              persistAndReset(sessionId, { error: 'Microphone unavailable or permission denied.' });
              return;
            }
            micHandle = handle;
          });
        },
        onError: (err) => {
          if (sessionId !== captureSessionId) return;
          console.error('[capture] STT error:', err);
          if (get().stream === next || isActiveSession(sessionId)) {
            persistAndReset(sessionId, {
              error: 'Speech capture failed to start. Check your connection and session.',
            });
          }
        },
        onClose: () => {
          if (sessionId !== captureSessionId) return;
          if (get().stream === next && (get().recording || get().connecting)) {
            persistAndReset(sessionId);
          }
        },
      },
      url,
    );

    set({ connecting: true, error: null, lastSegments: [], stream: next, source: 'mic' });
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

    const sessionId = ++captureSessionId;
    // Ensure no stale BLE audio monitor from a previous/debug session can
    // interfere before we open a new capture stream.
    omiBle.stopAudio();

    const vp = get().voiceprint;
    const next = new DeepgramStream(
      {
        onSegment: (seg) => {
          if (sessionId !== captureSessionId) return;
          if (!vp.isEnrolled()) vp.enroll(seg.speaker);
          const { label, isUser } = vp.labelForSpeaker(seg.speaker);
          get().pushSegment({ ...seg, speaker: label, isUser });
        },
        onOpen: () => {
          if (sessionId !== captureSessionId || get().stream !== next) return;
          set({ connecting: false, recording: true, error: null, source: 'omi' });
          // Device bytes are forwarded exactly as they arrive (payload already stripped).
          void omiBle.startAudio().then(async (ok) => {
            if (sessionId !== captureSessionId || get().stream !== next) return;
            if (!ok) {
              persistAndReset(sessionId, {
                error: `Could not enable device audio: ${omiBle.startAudioError() ?? 'unknown'}`,
              });
              return;
            }
            const subscribe = () => {
              omiBle.onAudio(
                (bytes) => {
                  if (sessionId !== captureSessionId || get().stream !== next) return;
                  next.sendAudio(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer);
                },
                (e) => {
                  if (sessionId !== captureSessionId || get().stream !== next) return;
                  const msg = e instanceof Error ? e.message : String(e);
                  console.error('[capture] omi audio error:', msg);
                  persistAndReset(sessionId, {
                    error: `Device audio stream failed: ${msg}. Reconnect the DevKit and try again.`,
                  });
                },
              );
            };
            try {
              subscribe();
            } catch (e) {
              const msg = e instanceof Error ? e.message : String(e);
              // One quick retry helps with transient BLE "Operation was cancelled" races.
              if (/cancel/i.test(msg)) {
                try {
                  await new Promise((r) => setTimeout(r, 250));
                  if (sessionId !== captureSessionId || get().stream !== next) return;
                  subscribe();
                  return;
                } catch (e2) {
                  if (sessionId !== captureSessionId) return;
                  console.error('[capture] omi audio retry failed:', e2);
                }
              }
              if (sessionId !== captureSessionId) return;
              console.error('[capture] omi audio subscribe error:', e);
              persistAndReset(sessionId, { error: `Device audio unavailable: ${msg}` });
            }
          });
        },
        onError: (err) => {
          if (sessionId !== captureSessionId) return;
          console.error('[capture] STT error:', err);
          if (get().stream === next || isActiveSession(sessionId)) {
            persistAndReset(sessionId, {
              error: 'Speech capture failed to start. Check your connection and session.',
            });
          }
        },
        onClose: () => {
          if (sessionId !== captureSessionId) return;
          if (get().stream === next && (get().recording || get().connecting)) {
            persistAndReset(sessionId);
          }
        },
      },
      url,
    );

    set({ connecting: true, error: null, lastSegments: [], stream: next, source: 'omi' });
    next.connect();
  },
  stop: () => {
    const sessionId = captureSessionId;
    captureSessionId++;
    persistAndReset(sessionId);
  },
  pushSegment: (seg) => {
    if (!useCaptureStore.getState().recording && !useCaptureStore.getState().connecting) return;
    set({ segments: [...get().segments, seg] });
  },
  /** Writes this session's segments to on-device storage. Called on stop(). */
}));
