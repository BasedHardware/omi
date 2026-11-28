import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  Pressable,
  TouchableOpacity,
  PermissionsAndroid,
  Platform,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/hooks/use-theme';
import { Spacing } from '@/constants/theme';
import {
  omiBle,
  type OmiCodec,
  type OmiIdentity,
  type OmiScanResult,
  type OmiState,
} from '@/services/omiBle';

/**
 * Connect an omi wearable. This is a product screen, not a debug one: pairing a
 * device is something an actual user has to do, and the "Connect" affordance on
 * Home already pointed at Settings with nothing behind it.
 *
 * Deliberately not gated on __DEV__ -- a release build has to be able to pair a
 * device. The dev screen keeps the parts that are only interesting while
 * debugging (raw chunk counters, per-step logs).
 *
 * Steps are separate actions rather than one "connect" flow because the failures
 * are per-stage: a device can connect and report a firmware revision while
 * refusing something else, and that is worth showing rather than swallowing.
 */

const CODEC_LABEL: Record<OmiCodec, string> = {
  pcm8: 'PCM 8-bit',
  pcm16: 'PCM 16-bit',
  opus: 'Opus',
  opusFS320: 'Opus (20 ms frames)',
  unknown: 'Unknown',
};

export default function OmiDeviceScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();

  const [adapter, setAdapter] = useState<OmiState | 'checking'>('checking');
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<OmiScanResult[]>([]);
  const [device, setDevice] = useState<OmiIdentity | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Read the adapter once on mount. `alive` guards against setting state after
  // the screen goes away, which is a real possibility when the user backs out
  // while the native call is still in flight.
  useEffect(() => {
    let alive = true;
    omiBle.state().then(
      (s) => {
        if (alive) setAdapter(s);
      },
      () => {
        if (alive) setAdapter('unsupported');
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  const ensurePermissions = useCallback(async (): Promise<boolean> => {
    if (Platform.OS !== 'android') return false;
    // Android 12+ moved BLE behind its own runtime grants. Below 12, scan
    // results are location data, so ACCESS_FINE_LOCATION is the grant that
    // actually matters there.
    const wanted =
      Number(Platform.Version) >= 31
        ? [
            PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN as never,
            PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT as never,
          ]
        : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION as never];
    const results = await PermissionsAndroid.requestMultiple(wanted);
    return Object.values(results).every((r) => r === PermissionsAndroid.RESULTS.GRANTED);
  }, []);

  const scan = useCallback(async () => {
    setError(null);
    if (!(await ensurePermissions())) {
      setError('Bluetooth permission was declined.');
      return;
    }
    setScanning(true);
    setFound([]);
    try {
      const results = await omiBle.scan(10);
      setFound(results);
      if (results.length === 0) {
        setError(
          'No device found. Wake the omi and check it is not already connected to another app.'
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setScanning(false);
    }
  }, [ensurePermissions]);

  const connect = useCallback(async (id: string) => {
    setError(null);
    setBusy(true);
    try {
      await omiBle.connect(id);
      // A device stamps recordings with its own clock, so this has to happen
      // before audio flows or every clip is filed against the wrong date.
      await omiBle.syncTime();
      setDevice(await omiBle.readIdentity());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const disconnect = useCallback(async () => {
    setBusy(true);
    try {
      await omiBle.disconnect();
      setDevice(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const connectedId = omiBle.connectedDeviceId;
  const battery = device?.batteryPct ?? null;
  const lowBattery = battery !== null && battery <= 10;

  return (
    <View style={[styles.root, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + Spacing.two, paddingBottom: 48 }}>
        <View style={styles.nav}>
          <Pressable
            style={styles.back}
            onPress={() => router.back()}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Text style={[styles.backText, { color: theme.text }]}>‹ Back</Text>
          </Pressable>
          <Text style={[styles.navTitle, { color: theme.text }]}>Wearable</Text>
        </View>

        <View style={styles.pad}>
          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {/* Adapter state first: every other answer depends on it, and a scan
              with Bluetooth off silently finds nothing. */}
          <Text style={[styles.label, { color: theme.textSecondary }]}>BLUETOOTH</Text>
          <View style={styles.adapterRow}>
            <View
              style={[
                styles.dot,
                {
                  backgroundColor:
                    adapter === 'ready'
                      ? '#4ade80'
                      : adapter === 'checking'
                        ? '#fbbf24'
                        : '#6b7280',
                },
              ]}
            />
            <Text style={[styles.body, { color: theme.text }]}>{adapterLabel(adapter)}</Text>
          </View>

          {device ? (
            <>
              <Text style={[styles.label, { color: theme.textSecondary }]}>CONNECTED</Text>
              <Card theme={theme}>
                <Row label="Name" value={device.name ?? '—'} theme={theme} />
                <Row label="Model" value={device.model ?? '—'} theme={theme} />
                <Row label="Firmware" value={device.firmware ?? '—'} theme={theme} />
                <Row label="Codec" value={CODEC_LABEL[device.codec]} theme={theme} />
                <Row
                  label="Battery"
                  value={battery === null ? '—' : `${battery}%`}
                  theme={theme}
                  warn={lowBattery}
                />
                {lowBattery ? (
                  <Text style={styles.warnText}>
                    Battery is very low. Charge it before streaming audio.
                  </Text>
                ) : null}
              </Card>
              <TouchableOpacity
                style={[styles.btn, { backgroundColor: '#b91c1c' }]}
                onPress={disconnect}
                disabled={busy}
              >
                <Text style={styles.btnText}>Disconnect</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <TouchableOpacity
                style={[
                  styles.btn,
                  { backgroundColor: scanning || adapter !== 'ready' ? '#374151' : '#2563eb' },
                ]}
                onPress={scan}
                disabled={scanning || adapter !== 'ready' || busy}
              >
                {scanning ? (
                  <View style={styles.btnInner}>
                    <ActivityIndicator color="#fff" size="small" />
                    <Text style={styles.btnText}>Scanning…</Text>
                  </View>
                ) : (
                  <Text style={styles.btnText}>Find my omi</Text>
                )}
              </TouchableOpacity>

              {found.length > 0 && (
                <>
                  <Text style={[styles.label, { color: theme.textSecondary }]}>FOUND</Text>
                  {found.map((d) => (
                    <TouchableOpacity
                      key={d.id}
                      style={[styles.deviceRow, { backgroundColor: theme.backgroundElement }]}
                      onPress={() => connect(d.id)}
                      disabled={busy}
                    >
                      <View style={styles.deviceText}>
                        <Text style={[styles.deviceName, { color: theme.text }]}>
                          {d.name ?? 'omi device'}
                        </Text>
                        <Text style={[styles.deviceMeta, { color: theme.textSecondary }]}>
                          {d.rssi !== null ? `${d.rssi} dBm` : d.id}
                        </Text>
                      </View>
                      {busy ? (
                        <ActivityIndicator color={theme.textSecondary} size="small" />
                      ) : (
                        <Text style={[styles.deviceAction, { color: '#60a5fa' }]}>Connect</Text>
                      )}
                    </TouchableOpacity>
                  ))}
                </>
              )}
            </>
          )}

          {connectedId && !device ? (
            <Text style={[styles.body, { color: theme.textSecondary }]}>
              Connected to {connectedId}. Reading device details…
            </Text>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

function adapterLabel(s: OmiState | 'checking'): string {
  switch (s) {
    case 'ready':
      return 'On and ready';
    case 'checking':
      return 'Checking…';
    case 'poweredOff':
      return 'Turned off — enable Bluetooth';
    case 'unauthorized':
      return 'Permission needed';
    default:
      return 'Not available on this device';
  }
}

function Row({
  label,
  value,
  theme,
  warn,
}: {
  label: string;
  value: string;
  theme: ReturnType<typeof useTheme>;
  warn?: boolean;
}) {
  return (
    <View style={styles.row}>
      <Text style={[styles.rowLabel, { color: theme.textSecondary }]}>{label}</Text>
      <Text
        style={[
          styles.rowValue,
          { color: warn ? '#fbbf24' : theme.text },
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

function Card({
  children,
  theme,
}: {
  children: React.ReactNode;
  theme: ReturnType<typeof useTheme>;
}) {
  return <View style={[styles.card, { backgroundColor: theme.backgroundElement }]}>{children}</View>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  pad: { paddingHorizontal: Spacing.three, gap: Spacing.two },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingBottom: Spacing.two,
  },
  back: { paddingVertical: 6 },
  backText: { fontSize: 16, fontWeight: '600' },
  navTitle: { fontSize: 20, fontWeight: '700' },
  label: { fontSize: 11, marginTop: Spacing.three },
  body: { fontSize: 14 },
  adapterRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  dot: { width: 8, height: 8, borderRadius: 4 },
  card: { borderRadius: 10, padding: Spacing.three, gap: Spacing.one },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: Spacing.two },
  rowLabel: { fontSize: 13 },
  rowValue: { fontSize: 13, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  warnText: { fontSize: 12, color: '#fbbf24', marginTop: Spacing.one },
  errorBox: {
    borderRadius: 8,
    padding: Spacing.two,
    backgroundColor: '#3f1d1d',
  },
  errorText: { color: '#fca5a5', fontSize: 13 },
  btn: { paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.two },
  btnInner: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 15 },
  deviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: Spacing.three,
    borderRadius: 10,
  },
  deviceText: { flex: 1 },
  deviceName: { fontSize: 15, fontWeight: '600' },
  deviceMeta: { fontSize: 12, marginTop: 2 },
  deviceAction: { fontSize: 14, fontWeight: '600' },
});