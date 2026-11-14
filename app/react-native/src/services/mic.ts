import { Platform, PermissionsAndroid } from 'react-native';
import LiveAudioStream from 'react-native-live-audio-stream';

/**
 * Microphone PCM capture for live speech recognition.
 *
 * Emits linear16 (signed 16-bit PCM) chunks as they are recorded so the caller
 * can push them over the authorized STT websocket. The sample format here MUST
 * match what the backend `/v4/listen` proxy expects (16 kHz mono 16-bit,
 * Android VOICE_RECOGNITION source) — change it only together with the backend
 * audio contract.
 */
const SAMPLE_RATE = 16000;
const CHANNELS = 1;
const BITS_PER_SAMPLE = 16;
const AUDIO_SOURCE = 6; // android MediaRecorder.AudioSource.VOICE_RECOGNITION
const BUFFER_SIZE = 4096;

const B64CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const B64LOOKUP: Record<string, number> = {};
B64CHARS.split('').forEach((c, i) => {
  B64LOOKUP[c] = i;
});

/** Decode a base64 string to a packed Uint8Array (no `buffer` polyfill needed). */
export function base64ToBytes(b64: string): Uint8Array {
  const s = b64.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((s.length * 3) / 4));
  let p = 0;
  for (let i = 0; i < s.length; i += 4) {
    const c0 = B64LOOKUP[s[i] ?? ''] ?? 0;
    const c1 = B64LOOKUP[s[i + 1] ?? ''] ?? 0;
    const c2 = B64LOOKUP[s[i + 2] ?? ''] ?? 0;
    const c3 = B64LOOKUP[s[i + 3] ?? ''] ?? 0;
    const n = (c0 << 18) | (c1 << 12) | (c2 << 6) | c3;
    if (p < out.length) out[p++] = (n >> 16) & 0xff;
    if (p < out.length) out[p++] = (n >> 8) & 0xff;
    if (p < out.length) out[p++] = n & 0xff;
  }
  return out;
}

export interface MicHandle {
  stop(): void;
}

/**
 * Request the mic, start streaming PCM, and hand each chunk to `onChunk`.
 * Resolves to a handle whose `stop()` tears the recorder down, or `null` if the
 * permission was denied / the native module failed to start. Errors go to `onError`.
 */
export async function startMic(
  onChunk: (bytes: ArrayBuffer) => void,
  onError: (err: unknown) => void,
): Promise<MicHandle | null> {
  if (Platform.OS === 'android') {
    try {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
        {
          title: 'Microphone access',
          message: 'Omi needs the microphone for live speech capture.',
          buttonNeutral: 'Later',
          buttonNegative: 'Cancel',
          buttonPositive: 'Allow',
        },
      );
      if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
        onError(new Error('Microphone permission denied'));
        return null;
      }
    } catch (e) {
      onError(e);
      return null;
    }
  }

  let active = true;
  try {
    LiveAudioStream.init({
      sampleRate: SAMPLE_RATE,
      channels: CHANNELS,
      bitsPerSample: BITS_PER_SAMPLE,
      audioSource: AUDIO_SOURCE,
      bufferSize: BUFFER_SIZE,
      wavFile: 'omi-live', // unused by the live-stream module; required by its type
    });
    LiveAudioStream.on('data', (data: string) => {
      if (!active) return;
      try {
        onChunk(base64ToBytes(data).buffer as ArrayBuffer);
      } catch (e) {
        onError(e);
      }
    });
    LiveAudioStream.start();
  } catch (e) {
    onError(e);
    return null;
  }

  return {
    stop() {
      active = false;
      try {
        void LiveAudioStream.stop();
      } catch {
        /* best-effort teardown */
      }
    },
  };
}
