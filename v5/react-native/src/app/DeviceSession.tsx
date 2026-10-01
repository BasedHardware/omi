import React, {useState} from 'react';
import {Platform, Text, View} from 'react-native';
import {
  isBluetoothScanAvailable,
  type PlatformNativeSnapshot,
} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {bluetoothStatusLabel} from './bluetooth';
import {DeviceControls} from './DeviceControls';
import {MaterialIcon} from '../ui/MaterialIcon';

import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {MobileGroup, MobileInlineState, MobileRow} from '../mobile/MobileList';

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
      <View accessibilityLabel="Remembered Omi device" style={styles.deviceRow}>
        <View style={styles.homeDeviceRowLead}>
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
            style={styles.scanButton}>
            <Text style={styles.scanButtonText}>Reconnect</Text>
          </FocusPressable>
        )}
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={`Forget ${rememberedDevice.name}`}
          disabled={deviceBusy || rememberedBusy}
          onPress={onForgetRemembered}
          style={styles.scanButton}>
          <Text style={styles.scanButtonText}>Forget</Text>
        </FocusPressable>
      </View>
    ) : null;

  if (mobile) {
    return (
      <MobileDevicePanel
        connected={devices.find(
          device => device.connected && !device.connecting,
        )}
        connectedLabel={connectedLabel}
        deviceBusy={deviceBusy}
        devices={devices}
        detailsId={detailsId}
        hint={hint}
        nativeSnapshot={nativeSnapshot}
        onForgetRemembered={onForgetRemembered}
        onScan={onScan}
        onToggle={onToggle}
        onToggleDetails={id =>
          setDetailsId(current => (current === id ? null : id))
        }
        rememberedBusy={rememberedBusy}
        rememberedDevice={rememberedDevice}
        scanDisabled={scanDisabled}
      />
    );
  }

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
    <View accessibilityLabel="Device information">
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

type PanelDevice = Device & {connecting: boolean};

/** The phone's device panel: one grouped surface in the Omi theme. */
function MobileDevicePanel({
  connected,
  connectedLabel,
  deviceBusy,
  devices,
  detailsId,
  hint,
  nativeSnapshot,
  onForgetRemembered,
  onScan,
  onToggle,
  onToggleDetails,
  rememberedBusy,
  rememberedDevice,
  scanDisabled,
}: {
  connected: PanelDevice | undefined;
  connectedLabel: string;
  deviceBusy: boolean;
  devices: PanelDevice[];
  detailsId: string | null;
  hint: string | null;
  nativeSnapshot: PlatformNativeSnapshot | null;
  onForgetRemembered?: () => void;
  onScan: () => void;
  onToggle: (id: string, connected: boolean) => void;
  onToggleDetails: (id: string) => void;
  rememberedBusy: boolean;
  rememberedDevice: {id: string; name: string} | null;
  scanDisabled: boolean;
}) {
  const theme = useOmiTheme();
  const panel = useOmiStyles(createPanelStyles);
  const expanded = connected !== undefined && detailsId === connected.id;
  return (
    <View accessibilityLabel="Home devices">
      <MobileGroup inset={52}>
        <MobileRow
          leading={
            <MaterialIcon
              name="bluetooth"
              color={theme.color.inkSecondary}
              size={theme.size.icon}
            />
          }
          title="Devices"
          subtitle={
            nativeSnapshot === null
              ? 'Checking Bluetooth…'
              : bluetoothStatusLabel(nativeSnapshot.bluetooth)
          }
          trailing={
            <View style={panel.action}>
              <OmiButton
                accessibilityLabel="Scan for Omi devices"
                compact
                disabled={scanDisabled}
                label={deviceBusy ? 'Please Wait…' : 'Scan'}
                onPress={onScan}
              />
            </View>
          }
        />
        {rememberedDevice && onForgetRemembered ? (
          <View accessibilityLabel="Remembered Omi device">
            <MobileRow
              leading={<View style={panel.dot} />}
              title={rememberedDevice.name}
              subtitle="Remembered device"
            />
            <View style={panel.actions}>
              {!devices.some(
                device => device.connected || device.connecting,
              ) && (
                <OmiButton
                  accessibilityLabel={`Reconnect ${rememberedDevice.name}`}
                  compact
                  disabled={deviceBusy || rememberedBusy}
                  label="Reconnect"
                  onPress={() => onToggle(rememberedDevice.id, false)}
                />
              )}
              <OmiButton
                accessibilityLabel={`Forget ${rememberedDevice.name}`}
                compact
                disabled={deviceBusy || rememberedBusy}
                label="Forget"
                onPress={onForgetRemembered}
              />
            </View>
          </View>
        ) : null}
        {devices.map(device => (
          <MobileRow
            key={device.id}
            accessibilityLabel={`${
              device.connecting
                ? 'Cancel connection to'
                : device.connected
                ? 'Disconnect'
                : 'Connect'
            } ${device.name}`}
            disabled={deviceBusy}
            onPress={() =>
              onToggle(device.id, device.connected || device.connecting)
            }
            leading={
              <View
                style={[
                  panel.dot,
                  device.connected && panel.dotLive,
                  device.connecting && panel.dotWaiting,
                ]}
              />
            }
            title={device.name}
            trailingText={
              device.battery !== undefined ? `${device.battery}%` : null
            }
            subtitle={
              device.connecting
                ? deviceBusy
                  ? 'Connecting…'
                  : 'Connecting… · Tap to cancel'
                : device.connected
                ? deviceBusy
                  ? connectedLabel
                  : `${connectedLabel} · Tap to disconnect`
                : device.rssi === undefined
                ? 'Signal unavailable'
                : `${device.rssi} dBm`
            }
          />
        ))}
        {connected ? (
          <View>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Device details"
              accessibilityState={{expanded}}
              onPress={() => onToggleDetails(connected.id)}
              style={({pressed}) => [
                panel.disclosure,
                pressed && panel.pressed,
              ]}>
              <Text style={panel.disclosureText}>
                Device Details & Controls
              </Text>
              <MaterialIcon
                name="expand_more"
                color={theme.color.inkTertiary}
                size={theme.size.icon}
                style={expanded ? panel.expanded : undefined}
              />
            </FocusPressable>
            <View
              accessibilityLabel="Device information"
              accessibilityElementsHidden={!expanded}
              importantForAccessibility={
                expanded ? 'auto' : 'no-hide-descendants'
              }
              style={expanded ? undefined : panel.hidden}>
              <DeviceControls
                key={connected.id}
                device={connected}
                busy={deviceBusy}
                mobile
              />
              <View style={panel.information}>
                {(
                  [
                    ['model', 'Model'],
                    ['firmware', 'Firmware'],
                    ['hardware', 'Hardware'],
                    ['manufacturer', 'Manufacturer'],
                    ['serial', 'Serial number'],
                  ] as const
                ).map(([field, label]) => (
                  <Text key={field} selectable style={panel.meta}>
                    {label}: {connected.information?.[field] ?? 'Unknown'}
                  </Text>
                ))}
              </View>
            </View>
          </View>
        ) : null}
        {hint !== null ? <MobileInlineState label={hint} /> : null}
      </MobileGroup>
    </View>
  );
}

const createPanelStyles = (t: OmiTheme) => ({
  action: {paddingRight: t.space.sm},
  actions: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: t.space.sm,
    paddingLeft: 52,
    paddingRight: t.space.lg,
    paddingBottom: t.space.md,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: t.color.inkTertiary,
  },
  dotLive: {backgroundColor: t.color.live},
  dotWaiting: {backgroundColor: t.color.warning},
  disclosure: {
    minHeight: 48,
    flexDirection: 'row' as const,
    gap: t.space.sm,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    paddingHorizontal: t.space.lg,
  },
  pressed: {backgroundColor: t.color.fillPressed},
  disclosureText: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    flexShrink: 1,
  },
  expanded: {transform: [{rotate: '180deg'}]},
  hidden: {display: 'none' as const},
  information: {
    gap: t.space.xs,
    paddingHorizontal: t.space.lg,
    paddingBottom: t.space.md,
  },
  meta: {...t.type.footnote, color: t.color.inkSecondary},
});
