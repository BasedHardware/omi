import React, {memo, useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {isNativeModuleInstalled, omiNative, type Device, type NativeSnapshot} from './src/omiNative';

type RuntimeState = 'loading' | 'ready' | 'unavailable' | 'error';

function Action({label, onPress, disabled}: {label: string; onPress: () => void; disabled?: boolean}) {
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[styles.action, disabled && styles.actionDisabled]}>
      <Text style={styles.actionText}>{label}</Text>
    </Pressable>
  );
}

const DeviceRow = memo(function DeviceRow({device, onPress, busy}: {device: Device; onPress: (device: Device) => void; busy: boolean}) {
  return (
    <View style={styles.deviceRow}>
      <View style={styles.deviceMark}><Text style={styles.deviceMarkText}>omi</Text></View>
      <View style={styles.deviceCopy}>
        <Text style={styles.deviceName}>{device.name}</Text>
        <Text style={styles.muted}>{device.rssi} dBm{device.battery == null ? '' : ` · ${device.battery}%`}</Text>
      </View>
      <Action label={device.connected ? 'Disconnect' : 'Connect'} onPress={() => onPress(device)} disabled={busy} />
    </View>
  );
});

function App(): React.JSX.Element {
  const [snapshot, setSnapshot] = useState<NativeSnapshot>();
  const [runtimeState, setRuntimeState] = useState<RuntimeState>('loading');
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!omiNative) {
      setRuntimeState('unavailable');
      return;
    }
    try {
      setSnapshot(await omiNative.getSnapshot());
      setRuntimeState('ready');
      setError(undefined);
    } catch (reason) {
      setRuntimeState('error');
      setError(reason instanceof Error ? reason.message : 'Native adapter did not return a state.');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run = useCallback(async (operation: () => Promise<void>) => {
    setBusy(true);
    try {
      await operation();
      await refresh();
    } catch (reason) {
      setRuntimeState('error');
      setError(reason instanceof Error ? reason.message : 'The native operation did not complete.');
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const scan = useCallback(() => {
    const native = omiNative;
    if (native) {
      run(async () => {
        await native.startScan(5, []);
      });
    }
  }, [run]);

  const toggleDevice = useCallback((device: Device) => {
    const native = omiNative;
    if (native) {
      run(async () => {
        if (device.connected) {
          await native.disconnectDevice(device.id);
        } else {
          await native.connectDevice(device.id);
        }
      });
    }
  }, [run]);

  const requestPermissions = useCallback(() => {
    const native = omiNative;
    if (native) {
      run(async () => {
        await native.requestPermissions();
      });
    }
  }, [run]);

  const status = runtimeState === 'loading'
    ? 'Checking the native platform…'
    : runtimeState === 'ready'
      ? snapshot?.lastEvent
      : runtimeState === 'unavailable'
        ? 'This platform has no Omi native adapter yet.'
        : error;

  return (
    <SafeAreaView style={styles.safe}>
      <FlatList
        data={snapshot?.devices ?? []}
        keyExtractor={(device) => device.id}
        renderItem={({item}) => <DeviceRow device={item} onPress={toggleDevice} busy={busy} />}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <>
            <View style={styles.topBar}>
              <Text style={styles.wordmark}>omi</Text>
              <Text style={styles.platform}>React Native</Text>
            </View>
            <Text style={styles.eyebrow}>YOUR DAY</Text>
            <Text style={styles.title}>A quiet place for what matters.</Text>
            <Text style={styles.subtitle}>Connect Omi to bring your day into view.</Text>
            <View style={styles.statusCard}>
              <View style={styles.statusHeading}>
                <Text style={styles.cardTitle}>Connection</Text>
                {runtimeState === 'loading' ? <ActivityIndicator color="#111111" /> : <Text style={styles.statusBadge}>{runtimeState}</Text>}
              </View>
              <Text style={styles.statusCopy}>{status}</Text>
              {snapshot ? <Text style={styles.muted}>Bluetooth: {snapshot.bluetooth} · Audio: {snapshot.audioRoute}</Text> : null}
              <View style={styles.actions}>
                <Action label={busy ? 'Working…' : 'Find my Omi'} onPress={scan} disabled={!isNativeModuleInstalled || busy} />
                <Action label="Permissions" onPress={requestPermissions} disabled={!isNativeModuleInstalled || busy} />
              </View>
            </View>
            <View style={styles.sectionHeading}>
              <Text style={styles.cardTitle}>Nearby Omi devices</Text>
              <Text style={styles.muted}>{snapshot?.devices.length ?? 0} found</Text>
            </View>
          </>
        }
        ListEmptyComponent={<Text style={styles.empty}>No nearby Omi devices are available.</Text>}
        ListFooterComponent={<Text style={styles.footer}>Memories, conversations, and tasks appear here after their shared client data bridge is connected.</Text>}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {flex: 1, backgroundColor: '#f7f7f5'},
  content: {padding: 24, gap: 12},
  topBar: {alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 48},
  wordmark: {color: '#111111', fontSize: 28, fontWeight: '900', letterSpacing: -1},
  platform: {color: '#6b6b6b', fontSize: 13, fontWeight: '600'},
  eyebrow: {color: '#6b6b6b', fontSize: 12, fontWeight: '800', letterSpacing: 1.2},
  title: {color: '#111111', fontSize: 40, fontWeight: '800', letterSpacing: -1.8, lineHeight: 44, marginTop: 12, maxWidth: 520},
  subtitle: {color: '#666666', fontSize: 17, lineHeight: 24, marginTop: 12, maxWidth: 440},
  statusCard: {backgroundColor: '#ffffff', borderColor: '#e3e3e0', borderRadius: 20, borderWidth: 1, gap: 12, marginTop: 32, padding: 20},
  statusHeading: {alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between'},
  cardTitle: {color: '#111111', fontSize: 18, fontWeight: '800'},
  statusBadge: {color: '#555555', fontSize: 12, fontWeight: '800', textTransform: 'uppercase'},
  statusCopy: {color: '#222222', fontSize: 16, lineHeight: 22},
  muted: {color: '#6b6b6b', fontSize: 13, lineHeight: 18},
  actions: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4},
  action: {backgroundColor: '#111111', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10},
  actionDisabled: {backgroundColor: '#d6d6d3'},
  actionText: {color: '#ffffff', fontSize: 13, fontWeight: '800'},
  sectionHeading: {alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginTop: 28, paddingBottom: 4},
  empty: {color: '#6b6b6b', fontSize: 15, lineHeight: 22, paddingBottom: 8},
  deviceRow: {alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#e3e3e0', borderRadius: 16, borderWidth: 1, flexDirection: 'row', gap: 12, padding: 14},
  deviceMark: {alignItems: 'center', borderColor: '#111111', borderRadius: 24, borderWidth: 1, height: 48, justifyContent: 'center', width: 48},
  deviceMarkText: {color: '#111111', fontSize: 11, fontWeight: '900'},
  deviceCopy: {flex: 1, gap: 3},
  deviceName: {color: '#111111', fontSize: 16, fontWeight: '800'},
  footer: {color: '#787878', fontSize: 12, lineHeight: 18, marginTop: 28, paddingBottom: 24},
});

export default App;
