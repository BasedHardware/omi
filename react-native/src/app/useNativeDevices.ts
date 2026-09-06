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

export function useNativeDevices(options?: {enabled?: boolean}) {
  const enabled = options?.enabled ?? true;
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
  );
  const nativeSnapshotRef = useRef<PlatformNativeSnapshot | null>(null);
  const sessionRef = useRef<string | null>(null);
  const openingRef = useRef(false);
  const flushPromiseRef = useRef<Promise<void> | null>(null);
  const cancelledRef = useRef(false);
  const pendingAudioRef = useRef<Uint8Array[]>([]);
  const uploadFailedRef = useRef(false);
  const epochRef = useRef(0);
  const enabledRef = useRef(enabled);

  enabledRef.current = enabled;

  nativeSnapshotRef.current = nativeSnapshot;

  const flushPendingAudio = useCallback(
    async (sessionId: string, epoch: number) => {
      if (!enabledRef.current || epoch !== epochRef.current) {
        return;
      }
      if (uploadFailedRef.current) {
        throw new Error('Device audio upload failed');
      }
      if (omiBackend === undefined || omiBackend === null) {
        return;
      }
      if (flushPromiseRef.current !== null) {
        await flushPromiseRef.current;
        if (
          enabledRef.current &&
          epoch === epochRef.current &&
          pendingAudioRef.current.length > 0 &&
          sessionRef.current === sessionId
        ) {
          await flushPendingAudio(sessionId, epoch);
        }
        return;
      }
      const work = (async () => {
        while (
          enabledRef.current &&
          epoch === epochRef.current &&
          pendingAudioRef.current.length > 0 &&
          sessionRef.current === sessionId
        ) {
          const chunk = pendingAudioRef.current.shift();
          if (chunk === undefined) {
            break;
          }
          await appendDeviceSessionAudio(omiBackend, sessionId, chunk);
        }
      })();
      flushPromiseRef.current = work;
      try {
        await work;
      } catch (error) {
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        uploadFailedRef.current = true;
        pendingAudioRef.current = [];
        setDeviceScanMessage(
          'Audio upload was interrupted. This recording could not be saved completely. Reconnect your Omi to start a new recording.',
        );
        throw error;
      } finally {
        if (flushPromiseRef.current === work) {
          flushPromiseRef.current = null;
        }
      }
      if (
        enabledRef.current &&
        epoch === epochRef.current &&
        pendingAudioRef.current.length > 0 &&
        sessionRef.current === sessionId
      ) {
        await flushPendingAudio(sessionId, epoch);
      }
    },
    [],
  );

  const finishSession = useCallback(async () => {
    const epoch = epochRef.current;
    if (!enabledRef.current) {
      return;
    }
    if (omiBackend === undefined || omiBackend === null) {
      cancelledRef.current = true;
      sessionRef.current = null;
      pendingAudioRef.current = [];
      return;
    }
    const sessionId = sessionRef.current;
    if (sessionId === null) {
      cancelledRef.current = true;
      return;
    }
    try {
      await flushPendingAudio(sessionId, epoch);
    } catch {
      return;
    }
    if (
      !enabledRef.current ||
      epoch !== epochRef.current ||
      sessionRef.current !== sessionId
    ) {
      return;
    }
    sessionRef.current = null;
    pendingAudioRef.current = [];
    cancelledRef.current = true;
    try {
      await completeDeviceSession(omiBackend, sessionId);
    } catch {
      return;
    }
  }, [flushPendingAudio]);

  const persistAudio = useCallback(
    async (event: Extract<OmiNativeEvent, {type: 'audio'}>) => {
      const epoch = epochRef.current;
      if (
        !enabledRef.current ||
        omiBackend === undefined ||
        omiBackend === null ||
        uploadFailedRef.current
      ) {
        return;
      }
      if (
        cancelledRef.current &&
        sessionRef.current === null &&
        !openingRef.current
      ) {
        return;
      }
      pendingAudioRef.current.push(bytesFromBase64(event.payloadBase64));
      if (sessionRef.current === null && !openingRef.current) {
        cancelledRef.current = false;
        openingRef.current = true;
        try {
          const snapshot = nativeSnapshotRef.current;
          const device = snapshot?.devices.find(
            item => item.id === event.deviceId,
          );
          const session = await openDeviceSession(omiBackend, {
            deviceId: event.deviceId,
            deviceName: device?.name,
            codec: event.codec,
          });
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          sessionRef.current = session.id;
        } catch {
          if (!enabledRef.current || epoch !== epochRef.current) {
            return;
          }
          pendingAudioRef.current = [];
          openingRef.current = false;
          uploadFailedRef.current = true;
          setDeviceScanMessage(
            'Audio upload could not start. Reconnect your Omi to start a new recording.',
          );
          return;
        }
        openingRef.current = false;
        if (cancelledRef.current) {
          await finishSession();
          return;
        }
      }
      const sessionId = sessionRef.current;
      if (sessionId === null) {
        return;
      }
      await flushPendingAudio(sessionId, epoch);
    },
    [finishSession, flushPendingAudio],
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
      sessionRef.current = null;
      openingRef.current = false;
      flushPromiseRef.current = null;
      cancelledRef.current = true;
      pendingAudioRef.current = [];
      uploadFailedRef.current = false;
      nativeSnapshotRef.current = null;
    };
    if (!enabled || omiNative === undefined || omiNative === null) {
      return retireSession;
    }
    omiNative
      .getSnapshot()
      .then(snapshot => {
        if (active) {
          setNativeSnapshot(snapshot);
        }
      })
      .catch(() => undefined);
    const unsubscribe = subscribeOmiNativeEvents(event => {
      if (!active) {
        return;
      }
      if (event.type === 'snapshot') {
        setNativeSnapshot(event.snapshot);
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
  }, [enabled, persistAudio]);

  useEffect(() => {
    if (
      nativeSnapshot !== null &&
      nativeSnapshot.capture !== 'recording' &&
      sessionRef.current !== null
    ) {
      finishSession().catch(() => undefined);
    }
  }, [finishSession, nativeSnapshot]);

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
      setNativeSnapshot({...snapshot, devices});
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
  }, []);

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
          if (uploadFailedRef.current) {
            uploadFailedRef.current = false;
            sessionRef.current = null;
            pendingAudioRef.current = [];
          }
          cancelledRef.current = false;
        }
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        const snapshot = await omiNative.getSnapshot();
        if (!enabledRef.current || epoch !== epochRef.current) {
          return;
        }
        setNativeSnapshot(snapshot);
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
    [finishSession],
  );

  return {
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  };
}
