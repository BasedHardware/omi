import {useEffect, useRef, useState} from 'react';
import {AppState, NativeModules, Platform} from 'react-native';

export type AmbientAudioStatus = {
  running: boolean;
  sinceMs: number | null;
  chunks: number;
  bytes: number;
  lastError: string | null;
};

type AmbientAudioNative = {
  requestMicrophonePermission(): Promise<'granted' | 'denied'>;
  startAmbientAudio(): Promise<void>;
  stopAmbientAudio(): Promise<void>;
  ambientAudioStatus(): Promise<AmbientAudioStatus>;
};

const AMBIENT_METHODS = [
  'requestMicrophonePermission',
  'startAmbientAudio',
  'stopAmbientAudio',
  'ambientAudioStatus',
] as const;

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

/**
 * Drives the native ambient microphone capture for the "always listen"
 * preference. The engine pauses while the Mac sleeps or locks and resumes on
 * wake; polling the native status keeps the UI honest about what is running.
 */
export function useAmbientAudio(
  mode: 'off' | 'always' | 'meetings',
  sessionReady: boolean,
) {
  const native = ambientAudioNative();
  const enabled = mode === 'always' && sessionReady;
  const [status, setStatus] = useState<AmbientAudioStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  return {
    available: native !== undefined,
    enabled,
    running: status?.running === true && enabled,
    status: enabled ? status : null,
    error,
  };
}
