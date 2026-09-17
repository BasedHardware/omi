import React, {useState} from 'react';
import {Platform, StyleSheet, Text, View} from 'react-native';
import {
  isBluetoothScanAvailable,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {bluetoothStatusLabel} from './bluetooth';
import {DeviceControls} from './DeviceControls';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import {mobileColor as color} from '../mobile/mobileTokens';

export type DeviceSessionVariant = 'affordance' | 'compact' | 'overview';

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
  const mobile = variant === 'compact' && Platform.OS !== 'macos';
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const connectedLabel =
    nativeSnapshot?.capture === 'recording' &&
    nativeSnapshot.audioStatus === 'waiting'
      ? 'Waiting for audio'
      : 'Connected';
  const scanDisabled =
    deviceBusy || !isBluetoothScanAvailable(nativeSnapshot?.bluetooth);
  const devices = (nativeSnapshot?.devices ?? []).map(device => ({
    ...device,
    connecting:
      nativeSnapshot?.phase === 'connecting' &&
      nativeSnapshot.connectedDeviceId === device.id,
  }));
  const hint =
    deviceScanMessage ??
    (nativeSnapshot !== null && devices.length === 0
      ? nativeSnapshot.lastEvent ?? 'No Omi device was discovered.'
      : null);

  const remembered =
    rememberedDevice && onForgetRemembered ? (
      <View
        accessibilityLabel="Remembered Omi device"
        style={[styles.deviceRow, mobile && local.remembered]}>
        <View
          style={[styles.homeDeviceRowLead, mobile && local.rememberedName]}>
          <Text numberOfLines={1} style={[styles.deviceName, {flexShrink: 1}]}>
            {rememberedDevice.name}
          </Text>
        </View>
        {!devices.some(device => device.connected || device.connecting) && (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel={`Reconnect ${rememberedDevice.name}`}
            disabled={deviceBusy || rememberedBusy}
            onPress={() => onToggle(rememberedDevice.id, false)}
            style={[styles.scanButton, mobile && local.action]}>
            <Text style={styles.scanButtonText}>Reconnect</Text>
          </FocusPressable>
        )}
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={`Forget ${rememberedDevice.name}`}
          disabled={deviceBusy || rememberedBusy}
          onPress={onForgetRemembered}
          style={[styles.scanButton, mobile && local.action]}>
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
              } ${device.name}`}
              accessibilityRole="button"
              disabled={deviceBusy}
              key={device.id}
              onPress={() =>
                onToggle(device.id, device.connected || device.connecting)
              }
              style={({pressed}) => [
                styles.macHomeDeviceChip,
                pressed && styles.pressed,
              ]}>
              <Text style={styles.macHomeDeviceChipText}>
                {device.name} ·{' '}
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
            onPress={onScan}
            style={({pressed}) => [
              styles.macHomeDeviceChip,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.macHomeDeviceChipText}>
              {deviceBusy ? 'Please wait…' : 'Devices'}
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
    <View style={[styles.deviceHeader, mobile && local.header]}>
      {variant === 'compact' ? (
        <View style={styles.homeDeviceHeading}>
          <View
            style={[
              styles.pendantStatusDot,
              {backgroundColor: bluetoothStatusColor},
            ]}
          />
          <View style={mobile && local.lead}>
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
          mobile && local.action,
          pressed && styles.pressed,
        ]}>
        <Text
          style={[
            styles.scanButtonText,
            variant === 'compact' && styles.homeScanButtonText,
          ]}>
          {deviceBusy ? 'Please wait…' : 'Scan'}
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
      } ${device.name}`}
      accessibilityRole="button"
      disabled={deviceBusy}
      key={device.id}
      onPress={() => onToggle(device.id, device.connected || device.connecting)}
      style={({pressed}) => [
        styles.deviceRow,
        variant === 'compact' && styles.homeDeviceRow,
        mobile && local.device,
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
          <View style={mobile && local.lead}>
            <Text style={styles.deviceName}>{device.name}</Text>
            <Text style={styles.deviceMeta}>
              {device.connecting
                ? mobile && !deviceBusy
                  ? 'Connecting… · Tap to cancel'
                  : 'Connecting…'
                : device.connected
                ? mobile && !deviceBusy
                  ? `${connectedLabel} · Tap to disconnect`
                  : connectedLabel
                : device.rssi === undefined
                ? 'Signal unavailable'
                : `${device.rssi} dBm`}
            </Text>
          </View>
        </View>
      ) : (
        <View>
          <Text style={styles.deviceName}>{device.name}</Text>
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
      {device.battery !== undefined && (
        <Text style={styles.deviceBattery}>{device.battery}%</Text>
      )}
    </FocusPressable>
  ));

  const connected = devices.find(
    device => device.connected && !device.connecting,
  );
  const information = connected ? (
    <View
      accessibilityLabel="Device information"
      accessibilityElementsHidden={mobile && detailsId !== connected.id}
      importantForAccessibility={
        mobile && detailsId !== connected.id ? 'no-hide-descendants' : 'auto'
      }
      style={mobile && detailsId !== connected.id ? local.hidden : undefined}>
      <DeviceControls key={connected.id} device={connected} busy={deviceBusy} />
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
          {label}: {connected.information?.[field] ?? 'Unknown'}
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
        <View style={[styles.homeDeviceCard, mobile && local.card]}>
          {header}
          {remembered}
          {rows}
          {mobile && connected && (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Device details"
              accessibilityState={{expanded: detailsId === connected.id}}
              onPress={() =>
                setDetailsId(current =>
                  current === connected.id ? null : connected.id,
                )
              }
              style={local.disclosure}>
              <Text style={local.disclosureText}>
                Device details & controls
              </Text>
              <ChevronDown
                color={color.textMuted}
                size={18}
                style={detailsId === connected.id ? local.expanded : undefined}
              />
            </FocusPressable>
          )}
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

const local = StyleSheet.create({
  card: {
    backgroundColor: color.surface,
    borderColor: color.border,
    borderRadius: 22,
    padding: 16,
    gap: 12,
  },
  header: {gap: 12},
  lead: {flex: 1},
  action: {minHeight: 44, alignItems: 'center'},
  device: {
    backgroundColor: color.surfaceQuiet,
    borderColor: color.border,
    paddingVertical: 14,
    gap: 8,
  },
  remembered: {flexWrap: 'wrap', gap: 8, paddingVertical: 12},
  rememberedName: {flexBasis: '100%'},
  disclosure: {
    minHeight: 48,
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  disclosureText: {color: color.textMuted, fontSize: 14, flexShrink: 1},
  expanded: {transform: [{rotate: '180deg'}]},
  hidden: {display: 'none'},
});
