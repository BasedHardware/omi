import React, {useCallback, useEffect, useState} from 'react';
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {isNativeModuleInstalled, omiNative, type CaptureMode, type Device, type NativeSnapshot} from './src/omiNative';

const initialSnapshot: NativeSnapshot = {
  bluetooth: 'unknown', devices: [], capture: 'idle', captureMode: 'stream', microphone: 'unknown',
  notifications: 'unknown', background: 'inactive', audioRoute: 'unknown', lastEvent: 'Loading native surface…',
};

function Action({label, onPress, disabled = false}: {label: string; onPress: () => void; disabled?: boolean}) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[styles.action, disabled && styles.disabled]}><Text style={styles.actionText}>{label}</Text></Pressable>;
}

function App(): React.JSX.Element {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => setSnapshot(await omiNative.getSnapshot()), []);
  useEffect(() => { refresh(); }, [refresh]);

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    try { await operation(); await refresh(); } finally { setBusy(false); }
  };

  const scan = () => run(() => omiNative.startScan(5, []));
  const toggleCapture = () => run(() => snapshot.capture === 'recording' ? omiNative.stopCapture() : omiNative.startCapture(snapshot.captureMode));
  const setMode = (mode: CaptureMode) => run(() => omiNative.startCapture(mode));

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.eyebrow}>OMI NATIVE MVP SPIKE</Text>
        <Text style={styles.title}>Device relay cockpit</Text>
        <Text style={styles.subtitle}>TypeScript UI · bounded native functions · no production code</Text>

        <View style={styles.statusCard}>
          <View style={styles.row}><Text style={styles.cardTitle}>Runtime</Text><Text style={styles.badge}>{isNativeModuleInstalled ? 'NATIVE' : 'HOST ADAPTER'}</Text></View>
          <Text style={styles.event}>{snapshot.lastEvent}</Text>
          <Text style={styles.muted}>Bluetooth: {snapshot.bluetooth} · Audio: {snapshot.audioRoute}</Text>
          <Text style={styles.muted}>Mic: {snapshot.microphone} · Notifications: {snapshot.notifications} · Background: {snapshot.background}</Text>
        </View>

        <View style={styles.card}>
          <View style={styles.row}><Text style={styles.cardTitle}>BLE devices</Text><Action label={busy ? 'Working…' : 'Scan'} onPress={scan} disabled={busy}/></View>
          {snapshot.devices.length === 0 ? <Text style={styles.muted}>No devices discovered. Run Scan to exercise the native seam.</Text> : snapshot.devices.map((device: Device) => (
            <View key={device.id} style={styles.deviceRow}>
              <View style={styles.deviceInfo}><Text style={styles.deviceName}>{device.name}</Text><Text style={styles.muted}>{device.id} · RSSI {device.rssi} · battery {device.battery}%</Text></View>
              <Action label={device.connected ? 'Disconnect' : 'Connect'} onPress={() => run(() => device.connected ? omiNative.disconnectDevice(device.id) : omiNative.connectDevice(device.id))} disabled={busy}/>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Capture and background</Text>
          <View style={styles.row}><Text style={styles.muted}>Mode: {snapshot.captureMode} · State: {snapshot.capture}</Text><Action label={snapshot.capture === 'recording' ? 'Stop' : 'Start'} onPress={toggleCapture} disabled={busy}/></View>
          <View style={styles.buttonRow}><Action label="Stream" onPress={() => setMode('stream')} disabled={busy}/><Action label="Batch" onPress={() => setMode('batch')} disabled={busy}/><Action label={snapshot.background === 'active' ? 'Disable background' : 'Enable background'} onPress={() => run(() => omiNative.setBackgroundMode(snapshot.background !== 'active'))} disabled={busy}/></View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Native capability coverage</Text>
          <Text style={styles.capability}>✓ BLE scan/connect/read/write/subscribe + RSSI diagnostics</Text>
          <Text style={styles.capability}>✓ Stream and batch capture lifecycle</Text>
          <Text style={styles.capability}>✓ Microphone, notifications, background, Wi-Fi, phone-call controls</Text>
          <Text style={styles.capability}>✓ Watch and camera status contracts</Text>
          <Text style={styles.capability}>○ Real platform implementation is the next gate</Text>
          <Action label="Request permissions" onPress={() => run(() => omiNative.requestPermissions())} disabled={busy}/>
        </View>

        <Text style={styles.footer}>Host adapter is deterministic. It proves TypeScript state, UI actions, and native contract shape; it does not claim BLE/audio hardware parity.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {flex: 1, backgroundColor: '#101214'},
  container: {padding: 20, gap: 14},
  eyebrow: {color: '#8fa3b8', fontSize: 12, fontWeight: '700', letterSpacing: 1.4},
  title: {color: '#f4f7fa', fontSize: 30, fontWeight: '800'},
  subtitle: {color: '#aeb9c5', fontSize: 14},
  card: {backgroundColor: '#1b2026', borderRadius: 14, padding: 16, gap: 12},
  statusCard: {backgroundColor: '#26313a', borderRadius: 14, padding: 16, gap: 8},
  cardTitle: {color: '#f4f7fa', fontSize: 18, fontWeight: '700'},
  row: {alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', gap: 12},
  buttonRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  badge: {backgroundColor: '#607d6c', borderRadius: 8, color: '#fff', fontSize: 11, fontWeight: '800', paddingHorizontal: 8, paddingVertical: 5},
  event: {color: '#dce8ef', fontSize: 15},
  muted: {color: '#aeb9c5', fontSize: 13},
  action: {backgroundColor: '#d8e3ea', borderRadius: 9, paddingHorizontal: 12, paddingVertical: 9},
  actionText: {color: '#101214', fontSize: 13, fontWeight: '800'},
  disabled: {opacity: 0.45},
  deviceRow: {alignItems: 'center', borderTopColor: '#343c45', borderTopWidth: 1, flexDirection: 'row', gap: 10, paddingTop: 12},
  deviceInfo: {flex: 1, gap: 3},
  deviceName: {color: '#f4f7fa', fontSize: 15, fontWeight: '700'},
  capability: {color: '#c9d4dc', fontSize: 13},
  footer: {color: '#7f8d99', fontSize: 12, lineHeight: 18, paddingBottom: 24},
});

export default App;
