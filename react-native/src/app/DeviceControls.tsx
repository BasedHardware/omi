import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {omiNative} from '../omiNative';
import type {Device, DeviceStorageStatus} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';

type Setting = 'ledBrightness' | 'microphoneGain';
const controls = [
  {
    setting: 'ledBrightness',
    label: 'LED brightness',
    bit: 7,
    maximum: 100,
    step: 10,
    unit: '%',
  },
  {
    setting: 'microphoneGain',
    label: 'Microphone gain',
    bit: 8,
    maximum: 8,
    step: 1,
    unit: '',
  },
] as const;

export function DeviceControls({
  device,
  busy,
}: {
  device: Device;
  busy: boolean;
}) {
  const [pending, setPending] = useState<
    Setting | 'findDevice' | 'storage' | null
  >(null);
  const [message, setMessage] = useState<string | null>(null);
  const [storage, setStorage] = useState<DeviceStorageStatus | null>(null);
  const active = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const write = async (setting: Setting, value: number) => {
    if (inFlight.current || !device.connected || !omiNative?.setDeviceSetting) {
      return;
    }
    inFlight.current = true;
    setPending(setting);
    setMessage(null);
    try {
      const confirmed = await omiNative.setDeviceSetting(
        device.id,
        setting,
        value,
      );
      if (confirmed !== value) {
        throw new Error('unconfirmed');
      }
      if (active.current) {
        setMessage('Confirmed on device');
      }
    } catch {
      if (active.current) {
        setMessage(
          'Could not confirm the change. Check the device and try again.',
        );
      }
    } finally {
      inFlight.current = false;
      if (active.current) {
        setPending(null);
      }
    }
  };

  const find = async () => {
    if (
      inFlight.current ||
      busy ||
      !device.connected ||
      !device.findDeviceSupported ||
      !omiNative?.findDevice
    ) {
      return;
    }
    inFlight.current = true;
    setPending('findDevice');
    setMessage(null);
    try {
      await omiNative.findDevice(device.id);
      if (active.current) {
        setMessage('Find device commands acknowledged. Check for vibration.');
      }
    } catch {
      if (active.current) {
        setMessage(
          'Could not send all find device commands. Check the connection and try again.',
        );
      }
    } finally {
      inFlight.current = false;
      if (active.current) {
        setPending(null);
      }
    }
  };

  const readStorage = async () => {
    if (
      inFlight.current ||
      busy ||
      !device.connected ||
      !device.storageStatusSupported ||
      !omiNative?.readStorageStatus
    ) {
      return;
    }
    inFlight.current = true;
    setPending('storage');
    setStorage(null);
    setMessage(null);
    try {
      const result = await omiNative.readStorageStatus(device.id);
      if (active.current) {
        setStorage(result);
      }
    } catch {
      if (active.current) {
        setMessage(
          'Storage status could not be read. The device may not support this format.',
        );
      }
    } finally {
      inFlight.current = false;
      if (active.current) {
        setPending(null);
      }
    }
  };

  return (
    <View accessibilityLabel="Device controls" style={local.container}>
      {device.connected && device.buttonSupported ? (
        <Text style={styles.deviceMeta}>
          Double-press to save this conversation and keep recording.
        </Text>
      ) : null}
      <Text style={styles.deviceMeta}>
        Charging:{' '}
        {device.charging === undefined
          ? 'Unknown'
          : device.charging
          ? 'Charging'
          : 'Not charging'}
      </Text>
      {device.connected &&
      device.findDeviceSupported &&
      omiNative?.findDevice ? (
        <FocusPressable
          accessibilityLabel="Find device"
          accessibilityRole="button"
          disabled={busy || pending !== null}
          onPress={find}
          style={styles.scanButton}>
          <Text style={styles.scanButtonText}>Find device</Text>
        </FocusPressable>
      ) : (
        <Text style={styles.deviceMeta}>Find device unavailable</Text>
      )}
      {device.connected &&
      device.storageStatusSupported &&
      omiNative?.readStorageStatus ? (
        <FocusPressable
          accessibilityLabel="Read storage status"
          accessibilityRole="button"
          disabled={busy || pending !== null}
          onPress={readStorage}
          style={styles.scanButton}>
          <Text style={styles.scanButtonText}>Read storage status</Text>
        </FocusPressable>
      ) : (
        <Text style={styles.deviceMeta}>Storage status unavailable</Text>
      )}
      {storage !== null && device.connected && (
        <View accessibilityLabel="Last reported storage status">
          <Text style={styles.deviceMeta}>Last reported storage</Text>
          <Text style={styles.deviceMeta}>
            Stored audio: {storage.usedBytes.toLocaleString()} bytes
          </Text>
          <Text style={styles.deviceMeta}>
            Unread packets: {storage.unreadPackets.toLocaleString()}
          </Text>
          <Text style={styles.deviceMeta}>
            Free space: {storage.freeBytes.toLocaleString()} bytes
          </Text>
          <Text style={styles.deviceMeta}>
            Device clock: {storage.clockValid ? 'Set' : 'Not set'}
          </Text>
        </View>
      )}
      {controls.map(control => {
        const value = device[control.setting];
        const features = device.features;
        const available =
          device.connected &&
          features !== undefined &&
          Number.isSafeInteger(features) &&
          features >= 0 &&
          features <= 0xffffffff &&
          Math.floor(features / 2 ** control.bit) % 2 === 1 &&
          value !== undefined &&
          Number.isInteger(value) &&
          value >= 0 &&
          value <= control.maximum;
        return (
          <View key={control.setting} style={local.row}>
            <Text style={[styles.deviceMeta, local.label]}>
              {control.label}:{' '}
              {available ? `${value}${control.unit}` : 'Unavailable'}
            </Text>
            {available && (
              <>
                <FocusPressable
                  accessibilityLabel={`Decrease ${control.label.toLowerCase()}`}
                  accessibilityRole="button"
                  disabled={
                    busy ||
                    pending !== null ||
                    !omiNative?.setDeviceSetting ||
                    value === 0
                  }
                  onPress={() => {
                    write(control.setting, Math.max(0, value! - control.step));
                  }}
                  style={styles.scanButton}>
                  <Text style={styles.scanButtonText}>−</Text>
                </FocusPressable>
                <FocusPressable
                  accessibilityLabel={`Increase ${control.label.toLowerCase()}`}
                  accessibilityRole="button"
                  disabled={
                    busy ||
                    pending !== null ||
                    !omiNative?.setDeviceSetting ||
                    value === control.maximum
                  }
                  onPress={() => {
                    write(
                      control.setting,
                      Math.min(control.maximum, value! + control.step),
                    );
                  }}
                  style={styles.scanButton}>
                  <Text style={styles.scanButtonText}>+</Text>
                </FocusPressable>
              </>
            )}
          </View>
        );
      })}
      {pending !== null && (
        <Text accessibilityRole="alert" style={styles.deviceMeta}>
          {pending === 'storage'
            ? 'Reading storage status…'
            : pending === 'findDevice'
            ? 'Sending find device commands…'
            : 'Confirming on device…'}
        </Text>
      )}
      {message !== null && (
        <Text accessibilityRole="alert" style={styles.deviceMeta}>
          {message}
        </Text>
      )}
    </View>
  );
}

const local = StyleSheet.create({
  container: {gap: 8, paddingVertical: 12},
  row: {flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap'},
  label: {flexGrow: 1, flexShrink: 1},
});
