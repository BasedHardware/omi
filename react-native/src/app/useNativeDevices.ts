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

export function useNativeDevices() {
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
  );
  const nativeSnapshotRef = useRef<PlatformNativeSnapshot | null>(null);
  const sessionRef = useRef<string | null>(null);
  const openingRef = useRef(false);
  const flushingRef = useRef(false);
  const cancelledRef = useRef(false);
  const pendingAudioRef = useRef<Uint8Array[]>([]);

  nativeSnapshotRef.current = nativeSnapshot;

  const finishSession = useCallback(async () => {
    cancelledRef.current = true;
    const sessionId = sessionRef.current;
    sessionRef.current = null;
    pendingAudioRef.current = [];
    if (sessionId === null || omiBackend === undefined || omiBackend === null) {
      return;
    }
    try {
      await completeDeviceSession(omiBackend, sessionId);
    } catch {
      return;
    }
  }, []);

  const flushPendingAudio = useCallback(async (sessionId: string) => {
    if (
      flushingRef.current ||
      omiBackend === undefined ||
      omiBackend === null
    ) {
      return;
    }
    flushingRef.current = true;
    try {
      while (
        pendingAudioRef.current.length > 0 &&
        !cancelledRef.current &&
        sessionRef.current === sessionId
      ) {
        const chunk = pendingAudioRef.current.shift();
        if (chunk === undefined) {
          break;
        }
        try {
          await appendDeviceSessionAudio(omiBackend, sessionId, chunk);
        } catch {
          return;
        }
      }
    } finally {
      flushingRef.current = false;
    }
    if (
      pendingAudioRef.current.length > 0 &&
      !cancelledRef.current &&
      sessionRef.current === sessionId
    ) {
      await flushPendingAudio(sessionId);
    }
  }, []);

  const persistAudio = useCallback(
    async (event: Extract<OmiNativeEvent, {type: 'audio'}>) => {
      if (omiBackend === undefined || omiBackend === null) {
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
          sessionRef.current = session.id;
        } catch {
          pendingAudioRef.current = [];
          openingRef.current = false;
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
      await flushPendingAudio(sessionId);
    },
    [finishSession, flushPendingAudio],
  );

  useEffect(() => {
    let active = true;
    if (omiNative === undefined || omiNative === null) {
      return () => undefined;
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
      active = false;
      unsubscribe();
    };
  }, [persistAudio]);

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
    if (omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    setDeviceScanMessage(null);
    try {
      const devices = await omiNative.startScan(8);
      const snapshot = await omiNative.getSnapshot();
      setNativeSnapshot({...snapshot, devices});
    } catch (error) {
      const message = browserScanErrorMessage(error);
      if (message !== null) {
        setDeviceScanMessage(message);
      }
    } finally {
      setDeviceBusy(false);
    }
  }, []);

  const toggleDevice = useCallback(
    async (id: string, connected: boolean) => {
      if (omiNative === undefined || omiNative === null) {
        return;
      }
      setDeviceBusy(true);
      try {
        if (connected) {
          await omiNative.disconnectDevice(id);
          await finishSession();
        } else {
          await omiNative.connectDevice(id);
        }
        setNativeSnapshot(await omiNative.getSnapshot());
      } catch {
        return;
      } finally {
        setDeviceBusy(false);
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
