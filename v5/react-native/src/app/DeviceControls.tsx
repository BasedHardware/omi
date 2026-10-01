import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {omiNative} from '../omiNative';
import type {Device, DeviceStorageStatus} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {useOmiStyles} from '../design/OmiTheme';
import {OmiButton} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';

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
  mobile = false,
}: {
  device: Device;
  busy: boolean;
  /** Phone styling from the Omi theme (the desktop keeps the kit styles). */
  mobile?: boolean;
}) {
  const themed = useOmiStyles(createMobileStyles);
  const meta = mobile ? themed.meta : styles.deviceMeta;
  const action = ({
    label,
    text,
    disabled,
    onPress,
  }: {
    label: string;
    text: string;
    disabled: boolean;
    onPress: () => void;
  }) =>
    mobile ? (
      <OmiButton
        accessibilityLabel={label}
        compact
        disabled={disabled}
        label={text}
        onPress={onPress}
      />
    ) : (
      <FocusPressable
        accessibilityLabel={label}
        accessibilityRole="button"
        disabled={disabled}
        onPress={onPress}
        style={[styles.scanButton, local.action]}>
        <Text style={styles.scanButtonText}>{text}</Text>
      </FocusPressable>
    );
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
    <View
      accessibilityLabel="Device controls"
      style={[local.container, mobile && themed.container]}>
      {device.connected && device.buttonSupported ? (
        <Text style={meta}>
          Double-press to save this conversation and keep recording.
        </Text>
      ) : null}
      <Text style={meta}>
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
        action({
          label: 'Find device',
          text: mobile ? 'Find Device' : 'Find device',
          disabled: busy || pending !== null,
          onPress: () => {
            find().catch(() => undefined);
          },
        })
      ) : (
        <Text style={meta}>Find device unavailable</Text>
      )}
      {device.connected &&
      device.storageStatusSupported &&
      omiNative?.readStorageStatus ? (
        action({
          label: 'Read storage status',
          text: mobile ? 'Read Storage Status' : 'Read storage status',
          disabled: busy || pending !== null,
          onPress: () => {
            readStorage().catch(() => undefined);
          },
        })
      ) : (
        <Text style={meta}>Storage status unavailable</Text>
      )}
      {storage !== null && device.connected && (
        <View accessibilityLabel="Last reported storage status">
          <Text style={meta}>Last reported storage</Text>
          <Text style={meta}>
            Stored audio: {storage.usedBytes.toLocaleString()} bytes
          </Text>
          <Text style={meta}>
            Unread packets: {storage.unreadPackets.toLocaleString()}
          </Text>
          <Text style={meta}>
            Free space: {storage.freeBytes.toLocaleString()} bytes
          </Text>
          <Text style={meta}>
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
            <Text style={[meta, local.label]}>
              {control.label}:{' '}
              {available ? `${value}${control.unit}` : 'Unavailable'}
            </Text>
            {available && (
              <>
                {action({
                  label: `Decrease ${control.label.toLowerCase()}`,
                  text: '−',
                  disabled:
                    busy ||
                    pending !== null ||
                    !omiNative?.setDeviceSetting ||
                    value === 0,
                  onPress: () => {
                    write(control.setting, Math.max(0, value! - control.step));
                  },
                })}
                {action({
                  label: `Increase ${control.label.toLowerCase()}`,
                  text: '+',
                  disabled:
                    busy ||
                    pending !== null ||
                    !omiNative?.setDeviceSetting ||
                    value === control.maximum,
                  onPress: () => {
                    write(
                      control.setting,
                      Math.min(control.maximum, value! + control.step),
                    );
                  },
                })}
              </>
            )}
          </View>
        );
      })}
      {pending !== null && (
        <Text accessibilityRole="alert" style={meta}>
          {pending === 'storage'
            ? 'Reading storage status…'
            : pending === 'findDevice'
            ? 'Sending find device commands…'
            : 'Confirming on device…'}
        </Text>
      )}
      {message !== null && (
        <Text accessibilityRole="alert" style={meta}>
          {message}
        </Text>
      )}
    </View>
  );
}

const createMobileStyles = (t: OmiTheme) => ({
  container: {paddingHorizontal: t.space.lg, paddingVertical: t.space.md},
  meta: {...t.type.footnote, color: t.color.inkSecondary},
});

const local = StyleSheet.create({
  container: {gap: 8, paddingVertical: 12},
  action: {minHeight: 44, minWidth: 44, alignItems: 'center'},
  row: {flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap'},
  label: {flexGrow: 1, flexShrink: 1},
});
