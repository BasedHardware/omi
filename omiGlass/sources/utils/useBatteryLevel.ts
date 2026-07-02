import * as React from 'react';
import { useBleCharacteristic } from './useBleCharacteristic';

// Standard BLE Battery Service UUIDs (SIG-defined)
const BATTERY_SERVICE_UUID = '0000180f-0000-1000-8000-00805f9b34fb';
const BATTERY_LEVEL_CHAR_UUID = '00002a19-0000-1000-8000-00805f9b34fb';

interface UseBatteryLevelResult {
  /** Battery level 0-100, or -1 if not yet read */
  level: number;
  /** Whether the battery notification is active */
  subscribed: boolean;
  /** Error message if subscription failed */
  error: string | null;
}

/**
 * Subscribe to BLE Battery Level notifications.
 *
 * Uses useBleCharacteristic under the hood, validating the hook
 * works across different BLE services (custom OMI vs standard SIG).
 *
 * The Battery Level characteristic (0x2A19) is a single byte 0-100.
 * The device sends a notification whenever the battery level changes.
 */
export function useBatteryLevel(device: BluetoothRemoteGATTServer): UseBatteryLevelResult {
  const [level, setLevel] = React.useState(-1);

  const onBatteryNotification = React.useCallback((e: Event) => {
    const value = (e.target as BluetoothRemoteGATTCharacteristic).value;
    if (value && value.byteLength > 0) {
      setLevel(value.getUint8(0));
    }
  }, []);

  const { subscribed, error } = useBleCharacteristic(device, {
    serviceUUID: BATTERY_SERVICE_UUID,
    characteristicUUID: BATTERY_LEVEL_CHAR_UUID,
    onCharacteristicChanged: onBatteryNotification,
  });

  return { level, subscribed, error };
}
