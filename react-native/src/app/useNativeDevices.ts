import {useCallback, useEffect, useState} from 'react';
import {
  browserScanErrorMessage,
  omiNative,
  type PlatformNativeSnapshot,
} from '../omiNative';

export function useNativeDevices() {
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
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
    return () => {
      active = false;
    };
  }, []);

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
      } else {
        // The native module owns the actual adapter error; preserve its last snapshot.
      }
    } finally {
      setDeviceBusy(false);
    }
  }, []);

  const toggleDevice = useCallback(async (id: string, connected: boolean) => {
    if (omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    try {
      if (connected) {
        await omiNative.disconnectDevice(id);
      } else {
        await omiNative.connectDevice(id);
      }
      setNativeSnapshot(await omiNative.getSnapshot());
    } catch {
      // Connection errors remain native-owned and are reflected on the next snapshot.
    } finally {
      setDeviceBusy(false);
    }
  }, []);

  return {
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  };
}
