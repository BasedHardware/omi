import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {omiNative} from '../omiNative';
import type {Device} from '../omiNativeTypes';
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
  const [pending, setPending] = useState<Setting | null>(null);
  const [message, setMessage] = useState<string | null>(null);
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

  return (
    <View accessibilityLabel="Device controls" style={local.container}>
      <Text style={styles.deviceMeta}>
        Charging:{' '}
        {device.charging === undefined
          ? 'Unknown'
          : device.charging
          ? 'Charging'
          : 'Not charging'}
      </Text>
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
          Confirming on device…
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
