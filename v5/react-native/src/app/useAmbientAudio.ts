import {useEffect, useRef, useState} from 'react';
import {AppState, NativeModules, Platform} from 'react-native';
import {decodeBase64} from '../base64';
import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  isTransientDeviceSessionError,
  openDeviceSession,
  transcribeDeviceSession,
} from '../deviceSessionClient';
import {
  isTransientLegacyOmiSyncError,
  LegacyOmiSyncError,
  syncLegacyOmiRecording,
} from '../legacyOmiSync';
import {omiBackend} from '../omiNative';

export type AmbientAudioStatus = {
  running: boolean;
  sinceMs: number | null;
  chunks: number;
  bytes: number;
  pendingSegments?: number;
  lastError: string | null;
};

export type AmbientSegmentRecord = {
  id: string;
  codec: number;
  capturedAtMs: number;
  packets: number;
  bytes: number;
};

type AmbientSegmentBatch = {
  codec: number;
  capturedAtMs: number;
  packets: string[];
  total: number;
  offset: number;
};

type AmbientAudioNative = {
  requestMicrophonePermission(): Promise<'granted' | 'denied'>;
  startAmbientAudio(): Promise<void>;
  stopAmbientAudio(): Promise<void>;
  ambientAudioStatus(): Promise<AmbientAudioStatus>;
  ambientAudioSegments(): Promise<AmbientSegmentRecord[]>;
  ambientAudioSegmentPackets(
    identifier: string,
    offset: number,
    limit: number,
  ): Promise<AmbientSegmentBatch>;
  ambientAudioAcknowledgeSegment(identifier: string): Promise<void>;
};

const AMBIENT_METHODS = [
  'requestMicrophonePermission',
  'startAmbientAudio',
  'stopAmbientAudio',
  'ambientAudioStatus',
  'ambientAudioSegments',
  'ambientAudioSegmentPackets',
  'ambientAudioAcknowledgeSegment',
] as const;

export const AMBIENT_AUDIO_DEVICE_ID = 'omi-macos-ambient';
export const AMBIENT_AUDIO_DEVICE_NAME = 'This Mac';
const UPLOAD_BATCH_PACKETS = 128;
const UPLOAD_RETRY_MS = 30_000;
const UPLOAD_BACKOFF_MS = 300_000;

export function ambientAudioNative(): AmbientAudioNative | undefined {
  if (Platform.OS !== 'macos') return undefined;
  const candidate = NativeModules.OmiRewind as
    | Record<string, unknown>
    | undefined;
  if (candidate === undefined) return undefined;
  return AMBIENT_METHODS.every(name => typeof candidate[name] === 'function')
    ? (candidate as unknown as AmbientAudioNative)
    : undefined;
}

async function ambientCaptureId(): Promise<string> {
  // Mirrors the native UUID v4 the journal path uses; a local fallback keeps
  // ambient upload working when the native generator is unavailable.
  const backend = omiBackend;
  if (
    backend !== null &&
    backend !== undefined &&
    backend.createRecordingId !== undefined
  ) {
    return backend.createRecordingId();
  }
  const bytes = new Uint8Array(16);
  for (let index = 0; index < 16; index += 1) {
    bytes[index] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(
    12,
    16,
  )}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function uploadAmbientSegment(
  native: AmbientAudioNative,
  segment: AmbientSegmentRecord,
): Promise<void> {
  const backend = omiBackend;
  if (backend === null || backend === undefined) {
    throw new Error('Native backend transport is unavailable');
  }
  if (backend.getApiContract !== undefined) {
    if ((await backend.getApiContract()) === 'omi') {
      // Legacy plane: the device-session endpoints do not exist there. Drain
      // the same framed packets through the wearable offline-sync pipeline so
      // conversations and memories build up on the account.
      const packets: Uint8Array[] = [];
      let offset = 0;
      while (offset < segment.packets) {
        const batch = await native.ambientAudioSegmentPackets(
          segment.id,
          offset,
          UPLOAD_BATCH_PACKETS,
        );
        if (batch.packets.length === 0) {
          throw new Error('Ambient audio segment ended early');
        }
        packets.push(...batch.packets.map(decodeBase64));
        offset += batch.packets.length;
      }
      await syncLegacyOmiRecording(backend, {
        capturedAtMs: segment.capturedAtMs,
        packets,
      });
      return;
    }
  }
  const captureId = await ambientCaptureId();
  const session = await openDeviceSession(backend, {
    captureId,
    capturedAtMs: segment.capturedAtMs,
    deviceId: AMBIENT_AUDIO_DEVICE_ID,
    deviceName: AMBIENT_AUDIO_DEVICE_NAME,
    codec: segment.codec,
  });
  let offset = 0;
  while (offset < segment.packets) {
    const batch = await native.ambientAudioSegmentPackets(
      segment.id,
      offset,
      UPLOAD_BATCH_PACKETS,
    );
    const packets = batch.packets.map(decodeBase64);
    if (packets.length === 0) {
      throw new Error('Ambient audio segment ended early');
    }
    await appendDeviceSessionAudio(backend, session.id, packets, offset);
    offset += packets.length;
  }
  await completeDeviceSession(backend, session.id);
  // The worker queue owns transcription; conversations appear as it finishes.
  void transcribeDeviceSession(backend, session.id).catch(() => undefined);
}

/**
 * Drives the native ambient microphone capture for the "always listen"
 * preference and drains the durable segment spool into the account's
 * device-sessions, which become conversations once transcribed. The engine
 * pauses while the Mac sleeps or locks and resumes on wake; polling the
 * native status keeps the UI honest about what is running.
 */
export function useAmbientAudio(
  mode: 'off' | 'always' | 'meetings',
  sessionReady: boolean,
) {
  const native = ambientAudioNative();
  const enabled = mode === 'always' && sessionReady;
  const [status, setStatus] = useState<AmbientAudioStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pendingUploads, setPendingUploads] = useState(0);
  const epoch = useRef(0);
  const active = useRef(false);
  const starting = useRef(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useRef(async () => {
    epoch.current += 1;
    active.current = false;
    starting.current = false;
    if (timer.current !== null) clearInterval(timer.current);
    timer.current = null;
    setStatus(null);
    try {
      await native?.stopAmbientAudio();
    } catch {
      /* stopping is best-effort */
    }
  });

  useEffect(() => {
    starting.current = false;
    active.current = false;
    if (!enabled || native === undefined) {
      setError(null);
      void stop.current();
      return;
    }
    const current = (epoch.current += 1);
    const valid = () => current === epoch.current;
    const poll = async () => {
      try {
        const next = await native.ambientAudioStatus();
        if (valid()) setStatus(next);
      } catch {
        /* transient */
      }
    };
    const ensure = async () => {
      if (!valid() || starting.current || active.current) return;
      starting.current = true;
      try {
        const permission = await native.requestMicrophonePermission();
        if (!valid()) return;
        if (permission !== 'granted') {
          setError(
            'Allow Microphone for this app in System Settings, then try again.',
          );
          return;
        }
        try {
          await native.startAmbientAudio();
        } catch (failure) {
          if (!valid()) return;
          const code =
            failure !== null && typeof failure === 'object' && 'code' in failure
              ? failure.code
              : null;
          setError(
            code === 'OMI_CAPTURE_PERMISSION'
              ? 'Allow Microphone for this app in System Settings, then try again.'
              : code === 'OMI_CAPTURE_UNAUTHORIZED'
              ? 'Sign in to use always-on listening.'
              : 'Always-on listening could not start. Check your microphone and try again.',
          );
          return;
        }
        if (!valid()) return;
        active.current = true;
        setError(null);
        await poll();
      } finally {
        if (valid()) starting.current = false;
      }
    };
    void ensure();
    timer.current = setInterval(() => {
      void poll();
    }, 5000);
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') void ensure();
    });
    return () => {
      epoch.current += 1;
      if (timer.current !== null) clearInterval(timer.current);
      timer.current = null;
      subscription.remove();
      void native.stopAmbientAudio().catch(() => undefined);
    };
  }, [enabled, native]);

  // Segment uploader: drains the durable spool whenever the session can
  // authenticate, so audio recorded before a restart still reaches the
  // account even when listening is off now.
  useEffect(() => {
    if (!sessionReady || native === undefined || omiBackend === undefined) {
      return;
    }
    let cancelled = false;
    let retry = setTimeout(() => undefined, 0) as unknown as ReturnType<
      typeof setTimeout
    >;
    const tick = async () => {
      let wait = UPLOAD_RETRY_MS;
      try {
        const segments = await native.ambientAudioSegments();
        if (segments.length > 0) setPendingUploads(segments.length);
        for (const segment of segments) {
          if (cancelled) return;
          try {
            await uploadAmbientSegment(native, segment);
            await native.ambientAudioAcknowledgeSegment(segment.id);
            setUploadError(null);
          } catch (failure) {
            if (
              failure instanceof LegacyOmiSyncError &&
              failure.unrecoverable
            ) {
              // Outside the server's recovery window: this audio can never be
              // admitted again, so drop it locally instead of jamming the
              // queue behind newer segments forever.
              await native.ambientAudioAcknowledgeSegment(segment.id);
              setUploadError(
                'Some recordings were older than the recovery window and could not sync.',
              );
              continue;
            }
            if (
              isTransientDeviceSessionError(failure) ||
              isTransientLegacyOmiSyncError(failure)
            ) {
              wait = UPLOAD_RETRY_MS;
            } else {
              wait = UPLOAD_BACKOFF_MS;
              setUploadError(
                'Recorded audio could not upload yet. It stays saved on this Mac and retries automatically.',
              );
            }
            break;
          }
        }
        const remaining = await native.ambientAudioSegments();
        if (!cancelled) setPendingUploads(remaining.length);
      } catch {
        /* native unavailable mid-drain; the next tick retries */
      }
      if (!cancelled) retry = setTimeout(() => void tick(), wait);
    };
    void tick();
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, [sessionReady, native]);

  return {
    available: native !== undefined,
    enabled,
    running: status?.running === true && enabled,
    status: enabled ? status : null,
    error,
    uploadError,
    pendingUploads,
  };
}
