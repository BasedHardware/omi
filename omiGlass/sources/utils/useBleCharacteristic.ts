import * as React from 'react';

interface UseBleCharacteristicOptions {
  /** Bluetooth service UUID to resolve */
  serviceUUID: string;
  /** Bluetooth characteristic UUID to subscribe to */
  characteristicUUID: string;
  /** Called when a notification value changes. Receives the raw Event. */
  onCharacteristicChanged: (event: Event) => void;
  /** Whether to auto-subscribe on mount (default: true) */
  enabled?: boolean;
}

interface UseBleCharacteristicResult {
  /** Whether the characteristic is currently subscribed to notifications */
  subscribed: boolean;
  /** Any error that occurred during subscription */
  error: string | null;
  /** Manually trigger re-subscription (e.g., after reconnect) */
  resubscribe: () => void;
}

/**
 * Reusable hook for subscribing to a BLE characteristic notification.
 *
 * Handles the full lifecycle:
 * 1. Resolves service + characteristic by UUID
 * 2. Calls startNotifications()
 * 3. Attaches 'characteristicvaluechanged' listener
 * 4. Cleans up listener + stopNotifications() on unmount
 * 5. Guards against race conditions with cancelled flag
 *
 * Usage:
 *   const { subscribed, error } = useBleCharacteristic({
 *     serviceUUID: '19b10000-...',
 *     characteristicUUID: '19b10001-...',
 *     onCharacteristicChanged: (e) => {
 *       const value = (e.target as BluetoothRemoteGATTCharacteristic).value;
 *       // process value...
 *     },
 *   });
 */
export function useBleCharacteristic(
  device: BluetoothRemoteGATTServer,
  options: UseBleCharacteristicOptions,
): UseBleCharacteristicResult {
  const {
    serviceUUID,
    characteristicUUID,
    onCharacteristicChanged,
    enabled = true,
  } = options;

  const [subscribed, setSubscribed] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [resubscribeKey, setResubscribeKey] = React.useState(0);

  // Stable ref for the callback to avoid re-subscribing on every render
  const callbackRef = React.useRef(onCharacteristicChanged);
  callbackRef.current = onCharacteristicChanged;

  const resubscribe = React.useCallback(() => {
    setResubscribeKey((k) => k + 1);
  }, []);

  React.useEffect(() => {
    if (!enabled || !device) return;

    let cancelled = false;
    let characteristicRef: BluetoothRemoteGATTCharacteristic | null = null;
    let handler: ((e: Event) => void) | null = null;

    (async () => {
      try {
        const service = await device.getPrimaryService(serviceUUID);
        if (cancelled) return;

        characteristicRef = await service.getCharacteristic(characteristicUUID);
        if (cancelled) return;

        await characteristicRef.startNotifications();
        if (cancelled) return;

        handler = (e: Event) => callbackRef.current(e);
        characteristicRef.addEventListener('characteristicvaluechanged', handler);

        if (!cancelled) {
          setSubscribed(true);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setSubscribed(false);
        }
      }
    })();

    // Cleanup: remove listener + stop notifications
    return () => {
      cancelled = true;
      if (characteristicRef && handler) {
        characteristicRef.removeEventListener('characteristicvaluechanged', handler);
        characteristicRef.stopNotifications().catch(() => {});
      }
      setSubscribed(false);
    };
  }, [device, serviceUUID, characteristicUUID, enabled, resubscribeKey]);

  return { subscribed, error, resubscribe };
}
