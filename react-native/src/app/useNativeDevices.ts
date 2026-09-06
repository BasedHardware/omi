import {useCallback, useEffect, useRef, useState} from 'react';
import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  openDeviceSession,
} from '../deviceSessionClient';
import {
  browserScanErrorMessage,
  omiBackend,
  omiNative,
  requestBluetoothScanPermission,
  subscribeOmiNativeEvents,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {OmiNativeEvent} from '../omiNativeTypes';

function bytesFromBase64(value: string): Uint8Array {
  const binary = globalThis.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function mergeDiscovery(
  snapshot: PlatformNativeSnapshot,
  event: Extract<OmiNativeEvent, {type: 'discovery'}>,
): PlatformNativeSnapshot {
  const devices = snapshot.devices.filter(
    device => device.id !== event.device.id,
  );
  return {
    ...snapshot,
    devices: [...devices, event.device].sort((left, right) =>
      left.id.localeCompare(right.id),
    ),
  };
}

function mergeBattery(
  snapshot: PlatformNativeSnapshot,
  event: Extract<OmiNativeEvent, {type: 'battery'}>,
): PlatformNativeSnapshot {
  return {
    ...snapshot,
    devices: snapshot.devices.map(device =>
      device.id === event.deviceId
        ? {...device, battery: event.battery}
        : device,
    ),
  };
}

type CaptureSession = {
  id: string | null;
  deviceId: string;
  codec: number;
  pending: Uint8Array[];
  work: Promise<void> | null;
  stopped: boolean;
  failed: boolean;
  completed: boolean;
};

export function useNativeDevices(options?: {enabled?: boolean}) {
  const enabled = options?.enabled ?? true;
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
  );
  const nativeSnapshotRef = useRef<PlatformNativeSnapshot | null>(null);
  const captureRef = useRef<CaptureSession | null>(null);
  const cancelledRef = useRef(false);
  const epochRef = useRef(0);
  const enabledRef = useRef(enabled);

  enabledRef.current = enabled;
  nativeSnapshotRef.current = nativeSnapshot;

  const processCapture = useCallback(
    (capture: CaptureSession, epoch: number): Promise<void> => {
      if (capture.work !== null) return capture.work;
      if (
        capture.failed ||
        capture.completed ||
        !enabledRef.current ||
        epoch !== epochRef.current ||
        omiBackend == null
      ) {
        return Promise.resolve();
      }
      const backend = omiBackend;
      const current = () => enabledRef.current && epoch === epochRef.current;
      const work = (async () => {
        try {
          if (capture.id === null) {
            const device = nativeSnapshotRef.current?.devices.find(
              item => item.id === capture.deviceId,
            );
            const session = await openDeviceSession(backend, {
              deviceId: capture.deviceId,
              deviceName: device?.name,
              codec: capture.codec,
            });
            if (!current()) return;
            capture.id = session.id;
          }
          while (current() && capture.pending.length > 0) {
            const chunk = capture.pending.shift()!;
            await appendDeviceSessionAudio(backend, capture.id, chunk);
          }
        } catch {
          if (!current()) return;
          capture.failed = true;
          capture.pending = [];
          setDeviceScanMessage(
            capture.id === null
              ? 'Audio upload could not start. Reconnect your Omi to start a new recording.'
              : 'Audio upload was interrupted. This recording could not be saved completely. Reconnect your Omi to start a new recording.',
          );
          return;
        }
        if (current() && capture.stopped) {
          capture.completed = true;
          try {
            await completeDeviceSession(backend, capture.id!);
          } catch {
            if (current()) {
              setDeviceScanMessage(
                'Audio was uploaded, but the recording could not be finalized. Its saved status is unconfirmed.',
              );
            }
          }
        }
      })();
      capture.work = work;
      void work.finally(() => {
        capture.work = null;
        if (
          current() &&
          !capture.failed &&
          !capture.completed &&
          (capture.pending.length > 0 || capture.stopped)
        ) {
          void processCapture(capture, epoch);
        }
      });
      return work;
    },
    [],
  );

  const finishSession = useCallback(async () => {
    cancelledRef.current = true;
    const capture = captureRef.current;
    captureRef.current = null;
    if (capture === null) return;
    capture.stopped = true;
    const work = processCapture(capture, epochRef.current);
    if (capture.id !== null) await work;
  }, [processCapture]);

  const persistAudio = useCallback(
    async (event: Extract<OmiNativeEvent, {type: 'audio'}>) => {
      if (!enabledRef.current || omiBackend == null || cancelledRef.current)
        return;
      let capture = captureRef.current;
      if (capture === null) {
        capture = {
          id: null,
          deviceId: event.deviceId,
          codec: event.codec,
          pending: [],
          work: null,
          stopped: false,
          failed: false,
          completed: false,
        };
        captureRef.current = capture;
      }
      if (
        capture.failed ||
        capture.deviceId !== event.deviceId ||
        capture.codec !== event.codec
      )
        return;
      capture.pending.push(bytesFromBase64(event.payloadBase64));
      await processCapture(capture, epochRef.current);
    },
    [processCapture],
  );

  const applySnapshot = useCallback(
    (snapshot: PlatformNativeSnapshot) => {
      const previous = nativeSnapshotRef.current;
      nativeSnapshotRef.current = snapshot;
      if (snapshot.capture !== 'recording' && captureRef.current !== null) {
        void finishSession();
      } else if (
        snapshot.capture === 'recording' &&
        previous?.capture !== 'recording'
      ) {
        cancelledRef.current = false;
      }
      setNativeSnapshot(snapshot);
    },
    [finishSession],
  );

  useEffect(() => {
    let active = true;
    cancelledRef.current = false;
    setNativeSnapshot(null);
    setDeviceBusy(false);
    setDeviceScanMessage(null);
    const retireSession = () => {
      active = false;
      epochRef.current += 1;
      captureRef.current = null;
      cancelledRef.current = true;
      nativeSnapshotRef.current = null;
    };
    if (!enabled || omiNative === undefined || omiNative === null) {
      return retireSession;
    }
    omiNative
      .getSnapshot()
      .then(snapshot => {
        if (active) {
          applySnapshot(snapshot);
        }
      })
      .catch(() => undefined);
    const unsubscribe = subscribeOmiNativeEvents(event => {
      if (!active) {
        return;
      }
      if (event.type === 'snapshot') {
        applySnapshot(event.snapshot);
        return;
      }
      if (event.type === 'discovery') {
        setNativeSnapshot(current =>
          current === null
            ? {
                bluetooth: 'poweredOn',
                devices: [event.device],
                connectedDeviceId: null,
                phase: 'disconnected',
                capture: 'idle',
                lastEvent: 'Found 1 Omi device',
                microphone: 'unknown',
                notifications: 'unknown',
              }
            : mergeDiscovery(current, event),
        );
        return;
      }
      if (event.type === 'battery') {
        setNativeSnapshot(current =>
          current === null ? current : mergeBattery(current, event),
        );
        return;
      }
      if (event.type === 'audio') {
        persistAudio(event).catch(() => undefined);
      }
    });
    return () => {
      retireSession();
      unsubscribe();
    };
  }, [applySnapshot, enabled, persistAudio]);

  const scanForOmi = useCallback(async () => {
    const epoch = epochRef.current;
    if (!enabledRef.current || omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    setDeviceScanMessage(null);
    try {
      const permitted = await requestBluetoothScanPermission();
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      if (!permitted) {
        setDeviceScanMessage(
          'Bluetooth permission is required to find your Omi. Allow it in app settings and try again.',
        );
        return;
      }
      const devices = await omiNative.startScan(8);
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      const snapshot = await omiNative.getSnapshot();
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      applySnapshot({...snapshot, devices});
    } catch (error) {
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      const message = browserScanErrorMessage(error);
      if (message !== null) {
        setDeviceScanMessage(message);
      } else {
        setDeviceScanMessage(
          'Could not scan for your Omi. Check Bluetooth and try again.',
        );
      }
    } finally {
      if (enabledRef.current && epoch === epochRef.current) {
        setDeviceBusy(false);
      }
    }
  }, [applySnapshot]);

  const toggleDevice = useCallback(
    async (id: string, connected: boolean) => {
      const epoch = epochRef.current;
      if (
        !enabledRef.current ||
        omiNative === undefined ||
        omiNative === null
      ) {
        return;
      }
      setDeviceBusy(true);
      try {
        if (connected) {
          await omiNative.disconnectDevice(id);
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          await finishSession();
        } else {
          await omiNative.connectDevice(id);
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          if (captureRef.current?.failed) captureRef.current = null;
          cancelledRef.current = false;
        }
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        const snapshot = await omiNative.getSnapshot();
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        applySnapshot(snapshot);
      } catch {
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        setDeviceScanMessage(
          connected
            ? 'Could not disconnect your Omi. Try again.'
            : 'Could not connect to your Omi. Keep it nearby and try again.',
        );
        return;
      } finally {
        if (enabledRef.current && epoch === epochRef.current) {
          setDeviceBusy(false);
        }
      }
    },
    [applySnapshot, finishSession],
  );

  return {
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  };
}
