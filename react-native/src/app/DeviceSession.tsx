import React from 'react';
import {Text, View} from 'react-native';
import {
  isBluetoothScanAvailable,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {bluetoothSessionLabel, emptyDeviceListHint} from './bluetooth';
import {DeviceControls} from './DeviceControls';
import {accountFieldCopy, deviceDisplayName} from '../desktopReadClient';

export type DeviceSessionVariant = 'affordance' | 'compact' | 'overview';

export function deviceHasReportedBattery(
  battery: number | undefined,
): battery is number {
  return typeof battery === 'number' && battery > 0;
}

export function homeConnectionStatus(snapshot: PlatformNativeSnapshot | null): {
  connectedDevice: Device | null;
  label: string;
  color: string;
} {
  if (snapshot?.phase === 'connecting') {
    return {
      connectedDevice: null,
      label: 'Connecting to Omi…',
      color: '#b4ad9f',
    };
  }
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
    const label =
      snapshot.bluetooth === 'poweredOn'
        ? 'Omi not connected'
        : bluetoothSessionLabel(snapshot);
    return {
      connectedDevice: null,
      label,
      color: label === 'Checking Bluetooth…' ? '#b4ad9f' : '#d9826f',
    };
  }
  return {
    connectedDevice,
    label: `Connected · ${
      snapshot.capture === 'recording'
        ? snapshot.audioStatus === 'waiting'
          ? 'Waiting for audio'
          : 'Listening'
        : 'Ready'
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
  rememberedDevice = null,
  rememberedBusy = false,
  onForgetRemembered,
}: {
  rememberedDevice?: {id: string; name: string} | null;
  rememberedBusy?: boolean;
  onForgetRemembered?: () => void;
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
  const connectedLabel =
    nativeSnapshot?.capture === 'recording'
      ? nativeSnapshot.audioStatus === 'waiting'
        ? 'Waiting for audio'
        : 'Listening'
      : 'Connected';
  const scanUnavailable = !isBluetoothScanAvailable(nativeSnapshot?.bluetooth);
  const scanDisabled = deviceBusy || scanUnavailable;
  const reconnectUnavailable =
    nativeSnapshot !== null &&
    !isBluetoothScanAvailable(nativeSnapshot.bluetooth);
  const connectUnavailable = (device: {
    connected?: boolean;
    connecting?: boolean;
  }) => scanUnavailable && !device.connected && !device.connecting;
  const devices = (nativeSnapshot?.devices ?? []).map(device => ({
    ...device,
    connecting:
      nativeSnapshot?.phase === 'connecting' &&
      nativeSnapshot.connectedDeviceId === device.id,
  }));
  const hint =
    deviceScanMessage ??
    (nativeSnapshot !== null && devices.length === 0
      ? emptyDeviceListHint(
          nativeSnapshot.lastEvent,
          nativeSnapshot.bluetooth,
          deviceBusy,
        )
      : null);

  const remembered =
    rememberedDevice && onForgetRemembered ? (
      <View accessibilityLabel="Remembered Omi device" style={styles.deviceRow}>
        <View style={styles.homeDeviceRowLead}>
          <Text numberOfLines={1} style={[styles.deviceName, {flexShrink: 1}]}>
            {deviceDisplayName(rememberedDevice.name)}
          </Text>
        </View>
        {!devices.some(device => device.connected || device.connecting) && (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel={`Reconnect ${deviceDisplayName(
              rememberedDevice.name,
            )}`}
            disabled={deviceBusy || rememberedBusy || reconnectUnavailable}
            onPress={
              reconnectUnavailable
                ? () => undefined
                : () => onToggle(rememberedDevice.id, false)
            }
            style={[
              styles.scanButton,
              reconnectUnavailable && styles.scanButtonUnavailable,
            ]}>
            <Text style={styles.scanButtonText}>Reconnect</Text>
          </FocusPressable>
        )}
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={`Forget ${deviceDisplayName(
            rememberedDevice.name,
          )}`}
          disabled={deviceBusy || rememberedBusy}
          onPress={onForgetRemembered}
          style={styles.scanButton}>
          <Text style={styles.scanButtonText}>Forget</Text>
        </FocusPressable>
      </View>
    ) : null;

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
                device.connecting
                  ? 'Cancel connection to'
                  : device.connected
                  ? 'Disconnect'
                  : 'Connect'
              } ${deviceDisplayName(device.name)}`}
              accessibilityRole="button"
              disabled={deviceBusy || connectUnavailable(device)}
              key={device.id}
              onPress={
                connectUnavailable(device)
                  ? () => undefined
                  : () =>
                      onToggle(device.id, device.connected || device.connecting)
              }
              style={({pressed}) => [
                styles.macHomeDeviceChip,
                connectUnavailable(device) && styles.scanButtonUnavailable,
                pressed && styles.pressed,
              ]}>
              <Text style={styles.macHomeDeviceChipText}>
                {deviceDisplayName(device.name)} ·{' '}
                {device.connecting
                  ? 'Connecting…'
                  : device.connected
                  ? connectedLabel
                  : 'Connect'}
              </Text>
            </FocusPressable>
          ))}
          <FocusPressable
            accessibilityLabel="Scan for Omi devices"
            accessibilityRole="button"
            disabled={scanDisabled}
            onPress={scanUnavailable ? () => undefined : onScan}
            style={({pressed}) => [
              styles.macHomeDeviceChip,
              scanUnavailable && styles.scanButtonUnavailable,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.macHomeDeviceChipText}>
              {deviceBusy ? 'Scanning…' : 'Devices'}
            </Text>
          </FocusPressable>
        </View>
        {remembered}
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
              {bluetoothSessionLabel(nativeSnapshot)}
            </Text>
          </View>
        </View>
      ) : (
        <View>
          <Text style={styles.sectionLabel}>Devices</Text>
          <Text style={styles.deviceState}>
            {bluetoothSessionLabel(nativeSnapshot)}
          </Text>
        </View>
      )}
      <FocusPressable
        accessibilityLabel="Scan for Omi devices"
        accessibilityRole="button"
        disabled={scanDisabled}
        onPress={scanUnavailable ? () => undefined : onScan}
        style={({pressed}) => [
          styles.scanButton,
          variant === 'compact' && styles.homeScanButton,
          scanUnavailable && styles.scanButtonUnavailable,
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
      accessibilityLabel={`${
        device.connecting
          ? 'Cancel connection to'
          : device.connected
          ? 'Disconnect'
          : 'Connect'
      } ${deviceDisplayName(device.name)}`}
      accessibilityRole="button"
      disabled={deviceBusy || connectUnavailable(device)}
      key={device.id}
      onPress={
        connectUnavailable(device)
          ? () => undefined
          : () => onToggle(device.id, device.connected || device.connecting)
      }
      style={({pressed}) => [
        styles.deviceRow,
        variant === 'compact' && styles.homeDeviceRow,
        connectUnavailable(device) && styles.scanButtonUnavailable,
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
            <Text style={styles.deviceName}>
              {deviceDisplayName(device.name)}
            </Text>
            <Text style={styles.deviceMeta}>
              {device.connecting
                ? 'Connecting…'
                : device.connected
                ? connectedLabel
                : device.rssi === undefined
                ? 'Signal unavailable'
                : `${device.rssi} dBm`}
            </Text>
          </View>
        </View>
      ) : (
        <View>
          <Text style={styles.deviceName}>
            {deviceDisplayName(device.name)}
          </Text>
          <Text style={styles.deviceMeta}>
            {device.connecting
              ? 'Connecting…'
              : device.connected
              ? connectedLabel
              : device.rssi === undefined
              ? 'Signal unavailable'
              : `${device.rssi} dBm`}
          </Text>
        </View>
      )}
      {deviceHasReportedBattery(device.battery) && (
        <Text style={styles.deviceBattery}>{`${device.battery}%`}</Text>
      )}
    </FocusPressable>
  ));

  const connected = devices.find(
    device => device.connected && !device.connecting,
  );
  const information = connected ? (
    <View accessibilityLabel="Device information">
      <DeviceControls key={connected.id} device={connected} busy={deviceBusy} />
      <Text selectable style={styles.deviceMeta}>
        Device ID
        {': '}
        {accountFieldCopy(connected.id, 'Unavailable')}
      </Text>
      {(
        [
          ['model', 'Model'],
          ['firmware', 'Firmware'],
          ['hardware', 'Hardware'],
          ['manufacturer', 'Manufacturer'],
          ['serial', 'Serial number'],
        ] as const
      ).map(([field, label]) => (
        <Text key={field} selectable style={styles.deviceMeta}>
          {label}
          {': '}
          {accountFieldCopy(connected.information?.[field], 'Unavailable')}
        </Text>
      ))}
    </View>
  ) : null;

  const hintRow =
    hint !== null ? <Text style={styles.deviceHint}>{hint}</Text> : null;

  if (variant === 'compact') {
    return (
      <View
        accessibilityLabel="Home devices"
        style={[styles.homeSection, styles.homeDevicesSection]}>
        <View style={styles.homeDeviceCard}>
          {header}
          {remembered}
          {rows}
          {information}
          {hintRow}
        </View>
      </View>
    );
  }

  return (
    <>
      {header}
      {remembered}
      {rows}
      {information}
      {hintRow}
    </>
  );
}
