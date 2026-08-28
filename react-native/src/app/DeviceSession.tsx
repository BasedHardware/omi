import React from 'react';
import {Text, View} from 'react-native';
import {
  isBluetoothScanAvailable,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {bluetoothStatusLabel} from './bluetooth';

export type DeviceSessionVariant = 'affordance' | 'compact' | 'overview';

export function homeConnectionStatus(snapshot: PlatformNativeSnapshot | null): {
  connectedDevice: Device | null;
  label: string;
  color: string;
} {
  const connectedDevice =
    snapshot?.devices.find(device => device.connected) ??
    snapshot?.devices.find(
      device => device.id === snapshot.connectedDeviceId,
    ) ??
    null;
  if (snapshot === null) {
    return {
      connectedDevice: null,
      label: 'Checking Bluetooth…',
      color: '#b4ad9f',
    };
  }
  if (connectedDevice === null) {
    return {
      connectedDevice: null,
      label:
        snapshot.bluetooth === 'poweredOn'
          ? 'Omi disconnected'
          : bluetoothStatusLabel(snapshot.bluetooth),
      color: '#d9826f',
    };
  }
  return {
    connectedDevice,
    label: `Connected · ${
      snapshot.capture === 'recording' ? 'Listening' : 'Ready'
    }`,
    color: '#45b79b',
  };
}

export function DeviceSession({
  bluetoothStatusColor,
  deviceBusy,
  deviceScanMessage,
  homeStatus,
  homeStatusColor,
  nativeSnapshot,
  onScan,
  onToggle,
  variant,
}: {
  bluetoothStatusColor?: string;
  deviceBusy: boolean;
  deviceScanMessage: string | null;
  homeStatus?: string;
  homeStatusColor?: string;
  nativeSnapshot: PlatformNativeSnapshot | null;
  onScan: () => void;
  onToggle: (id: string, connected: boolean) => void;
  variant: DeviceSessionVariant;
}): React.JSX.Element {
  const scanDisabled =
    deviceBusy || !isBluetoothScanAvailable(nativeSnapshot?.bluetooth);
  const devices = nativeSnapshot?.devices ?? [];
  const hint =
    deviceScanMessage ??
    (nativeSnapshot !== null && devices.length === 0
      ? nativeSnapshot.lastEvent ?? 'No Omi device was discovered.'
      : null);

  if (variant === 'affordance') {
    return (
      <View
        accessibilityLabel="Home device affordance"
        style={styles.macHomeDeviceAffordance}>
        <View style={styles.macHomeDeviceStatus}>
          <View
            style={[
              styles.pendantStatusDot,
              {backgroundColor: homeStatusColor},
            ]}
          />
          <Text style={styles.macHomeDeviceStatusText}>{homeStatus}</Text>
        </View>
        <View style={styles.macHomeDeviceActions}>
          {devices.map(device => (
            <FocusPressable
              accessibilityLabel={`${
                device.connected ? 'Disconnect' : 'Connect'
              } ${device.name}`}
              accessibilityRole="button"
              disabled={deviceBusy}
              key={device.id}
              onPress={() => onToggle(device.id, device.connected)}
              style={({pressed}) => [
                styles.macHomeDeviceChip,
                pressed && styles.pressed,
              ]}>
              <Text style={styles.macHomeDeviceChipText}>
                {device.name} · {device.connected ? 'Connected' : 'Connect'}
              </Text>
            </FocusPressable>
          ))}
          <FocusPressable
            accessibilityLabel="Scan for Omi devices"
            accessibilityRole="button"
            disabled={scanDisabled}
            onPress={onScan}
            style={({pressed}) => [
              styles.macHomeDeviceChip,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.macHomeDeviceChipText}>
              {deviceBusy ? 'Scanning…' : 'Devices'}
            </Text>
          </FocusPressable>
        </View>
        {deviceScanMessage !== null && (
          <Text style={styles.macHomeDeviceHint}>{deviceScanMessage}</Text>
        )}
      </View>
    );
  }

  const header = (
    <View style={styles.deviceHeader}>
      {variant === 'compact' ? (
        <View style={styles.homeDeviceHeading}>
          <View
            style={[
              styles.pendantStatusDot,
              {backgroundColor: bluetoothStatusColor},
            ]}
          />
          <View>
            <Text style={[styles.sectionLabel, styles.homeSectionLabel]}>
              Devices
            </Text>
            <Text style={[styles.deviceState, styles.homeDeviceState]}>
              {nativeSnapshot === null
                ? 'Checking Bluetooth…'
                : bluetoothStatusLabel(nativeSnapshot.bluetooth)}
            </Text>
          </View>
        </View>
      ) : (
        <View>
          <Text style={styles.sectionLabel}>Devices</Text>
          <Text style={styles.deviceState}>
            {nativeSnapshot === null
              ? 'Checking Bluetooth…'
              : bluetoothStatusLabel(nativeSnapshot.bluetooth)}
          </Text>
        </View>
      )}
      <FocusPressable
        accessibilityLabel="Scan for Omi devices"
        accessibilityRole="button"
        disabled={scanDisabled}
        onPress={onScan}
        style={({pressed}) => [
          styles.scanButton,
          variant === 'compact' && styles.homeScanButton,
          pressed && styles.pressed,
        ]}>
        <Text
          style={[
            styles.scanButtonText,
            variant === 'compact' && styles.homeScanButtonText,
          ]}>
          {deviceBusy ? 'Scanning…' : 'Scan'}
        </Text>
      </FocusPressable>
    </View>
  );

  const rows = devices.map(device => (
    <FocusPressable
      accessibilityLabel={`${device.connected ? 'Disconnect' : 'Connect'} ${
        device.name
      }`}
      accessibilityRole="button"
      disabled={deviceBusy}
      key={device.id}
      onPress={() => onToggle(device.id, device.connected)}
      style={({pressed}) => [
        styles.deviceRow,
        variant === 'compact' && styles.homeDeviceRow,
        pressed && styles.pressed,
      ]}>
      {variant === 'compact' ? (
        <View style={styles.homeDeviceRowLead}>
          <View
            style={[
              styles.homeDeviceRowDot,
              device.connected && styles.homeDeviceRowDotConnected,
            ]}
          />
          <View>
            <Text style={styles.deviceName}>{device.name}</Text>
            <Text style={styles.deviceMeta}>
              {device.connected ? 'Connected' : `${device.rssi} dBm`}
            </Text>
          </View>
        </View>
      ) : (
        <View>
          <Text style={styles.deviceName}>{device.name}</Text>
          <Text style={styles.deviceMeta}>
            {device.connected ? 'Connected' : `${device.rssi} dBm`}
          </Text>
        </View>
      )}
      {device.battery !== undefined && (
        <Text style={styles.deviceBattery}>{device.battery}%</Text>
      )}
    </FocusPressable>
  ));

  const hintRow =
    hint !== null ? <Text style={styles.deviceHint}>{hint}</Text> : null;

  if (variant === 'compact') {
    return (
      <View
        accessibilityLabel="Home devices"
        style={[styles.homeSection, styles.homeDevicesSection]}>
        <View style={styles.homeDeviceCard}>
          {header}
          {rows}
          {hintRow}
        </View>
      </View>
    );
  }

  return (
    <>
      {header}
      {rows}
      {hintRow}
    </>
  );
}
