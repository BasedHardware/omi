import {useCallback, useEffect, useRef, useState} from 'react';
import {NativeModules, Platform} from 'react-native';

type CaptureNative = {
  requestCapturePermission(): Promise<
    'granted' | 'denied' | 'restartRequired' | 'unsupported'
  >;
  startCapture(): Promise<void>;
  stopCapture(): Promise<void>;
  captureFrame(): Promise<{captured: boolean}>;
};

export function useRewindCapture(enabled: boolean, onCaptured: () => void) {
  const candidate =
    Platform.OS === 'macos'
      ? (NativeModules.OmiRewind as CaptureNative | undefined)
      : undefined;
  const native =
    candidate !== undefined &&
    [
      'requestCapturePermission',
      'startCapture',
      'stopCapture',
      'captureFrame',
    ].every(
      name => typeof candidate[name as keyof CaptureNative] === 'function',
    )
      ? candidate
      : undefined;
  const [capturing, setCapturing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const epoch = useRef(0);
  const active = useRef(false);
  const starting = useRef(false);
  const enabledRef = useRef(enabled);
  const capturedRef = useRef(onCaptured);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wake = useRef<(() => void) | null>(null);
  enabledRef.current = enabled;
  capturedRef.current = onCaptured;
  const stop = useCallback(async () => {
    const stoppedEpoch = (epoch.current += 1);
    active.current = false;
    starting.current = false;
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    wake.current?.();
    wake.current = null;
    setCapturing(false);
    setBusy(false);
    try {
      await native?.stopCapture();
    } catch {
      if (epoch.current === stoppedEpoch && enabledRef.current)
        setError(
          'Could not confirm capture stopped. Restart this app before capturing again.',
        );
    }
  }, [native]);
  useEffect(() => {
    if (!enabled) {
      setError(null);
      void stop();
    }
    return () => {
      epoch.current += 1;
      active.current = false;
      starting.current = false;
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
      wake.current?.();
      wake.current = null;
      void native?.stopCapture().catch(() => undefined);
    };
  }, [enabled, native, stop]);
  const start = useCallback(async () => {
    if (
      !enabledRef.current ||
      native === undefined ||
      starting.current ||
      active.current
    )
      return;
    const current = (epoch.current += 1);
    const valid = () => current === epoch.current && enabledRef.current;
    starting.current = true;
    setBusy(true);
    setError(null);
    try {
      const permission = await native.requestCapturePermission();
      if (!valid()) return;
      if (permission !== 'granted') {
        setError(
          permission === 'restartRequired'
            ? 'Restart this app to use the newly granted screen recording permission.'
            : permission === 'unsupported'
            ? 'Screen capture requires macOS 14 or later.'
            : 'Allow Screen Recording for this app in System Settings, then try again.',
        );
        return;
      }
      await native.startCapture();
      if (!valid()) return;
      active.current = true;
      starting.current = false;
      setBusy(false);
      setCapturing(true);
      while (valid() && active.current) {
        const result = await native.captureFrame();
        if (!valid() || !active.current) return;
        if (result.captured) capturedRef.current();
        await new Promise<void>(resolve => {
          wake.current = resolve;
          timer.current = setTimeout(() => {
            timer.current = null;
            wake.current = null;
            resolve();
          }, 3000);
        });
      }
    } catch (failure) {
      if (valid()) {
        const code =
          failure !== null && typeof failure === 'object' && 'code' in failure
            ? failure.code
            : null;
        setError(
          code === 'OMI_CAPTURE_QUOTA'
            ? 'Capture stopped because this app’s Rewind storage reached its 1 GB limit.'
            : code === 'OMI_CAPTURE_STOPPED'
            ? 'Capture stopped. Start again when your Mac is unlocked and this account is ready.'
            : 'Capture stopped because a frame could not be saved. Check permission and available storage, then try again.',
        );
        await stop().catch(() => undefined);
      }
    } finally {
      if (valid()) {
        starting.current = false;
        setBusy(false);
      }
    }
  }, [native, stop]);
  return {
    available: native?.captureFrame !== undefined,
    capturing,
    busy,
    error,
    start,
    stop,
  };
}
