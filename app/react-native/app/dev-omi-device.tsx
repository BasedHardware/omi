import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  PermissionsAndroid,
  Platform,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/hooks/use-theme';
import { Spacing } from '@/constants/theme';
import { DEV_LOCAL_BRAIN } from '@/devFlags';
import { useCaptureStore } from '@/state/captureStore';
import {
  omiBle,
  OMI,
  SAMPLE_RATE,
  type OmiIdentity,
  type OmiScanResult,
  type OmiState,
} from '@/services/omiBle';

/**
 * DEV-ONLY screen for bringing up an omi wearable over BLE.
 *
 * Gated on DEV_LOCAL_BRAIN, same as the local-brain screen -- see devFlags.ts.
 *
 * Every step is a separate button rather than one "connect" flow, because the
 * interesting failures are per-characteristic: a device can connect and report a
 * firmware revision while refusing the audio notify write, and that is worth
 * seeing rather than having swallowed by a single try/catch.
 */
export default function DevOmiDeviceScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();

  const [bleState, setBleState] = useState<OmiState | 'checking'>('checking');
  const [scanning, setScanning] = useState(false);
  const [found, setFound] = useState<OmiScanResult[]>([]);
  const [identity, setIdentity] = useState<OmiIdentity | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [audioChunks, setAudioChunks] = useState(0);
  const [audioBytes, setAudioBytes] = useState(0);
  const [listening, setListening] = useState(false);
  const capture = useCaptureStore();

  const say = useCallback((line: string) => {
    setLog((p) => [line, ...p].slice(0, 14));
  }, []);

  const ensurePermissions = useCallback(async (): Promise<boolean> => {
    if (Platform.OS !== 'android') return false;
    // Android 12+ split BLE out of location. Below 12, scan results are location
    // data, so ACCESS_FINE_LOCATION is the grant that actually matters there.
    const wanted =
      Number(Platform.Version) >= 31
        ? [
            PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN as never,
            PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT as never,
          ]
        : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION as never];
    const results = await PermissionsAndroid.requestMultiple(wanted);
    const ok = Object.values(results).every((r) => r === PermissionsAndroid.RESULTS.GRANTED);
    say(ok ? 'permissions granted' : `permissions ${JSON.stringify(results)}`);
    return ok;
  }, [say]);

  useEffect(() => {
    omiBle
      .state()
      .then((s) => {
        setBleState(s);
        say(`adapter state: ${s}`);
      })
      .catch((e) => say(`state error: ${String(e)}`));
  }, [say]);

  const scan = useCallback(async () => {
    if (!(await ensurePermissions())) return;
    setScanning(true);
    setFound([]);
    say(`scanning for ${OMI.service}...`);
    try {
      const r = await omiBle.scan(10);
      setFound(r);
      say(r.length ? `found ${r.length}: ${r.map((d) => d.name ?? d.id).join(', ')}` : 'found nothing');
    } catch (e) {
      say(`scan failed: ${String(e)}`);
    } finally {
      setScanning(false);
    }
  }, [ensurePermissions, say]);

  const connect = useCallback(
    async (id: string) => {
      say(`connecting ${id}...`);
      try {
        const d = await omiBle.connect(id);
        say(`connected: ${d.name ?? d.id}`);
        const synced = await omiBle.syncTime();
        say(synced ? 'time synced' : 'time sync FAILED (non-fatal)');
        const ident = await omiBle.readIdentity();
        setIdentity(ident);
        say(
          `codec=${ident.codec} battery=${ident.batteryPct ?? '?'} fw=${ident.firmware ?? '?'}`
        );
      } catch (e) {
        say(`connect failed: ${String(e)}`);
      }
    },
    [say]
  );

  const startAudio = useCallback(async () => {
    try {
      const enabled = await omiBle.startAudio();
      if (!enabled) {
        say(`CCCD write FAILED: ${omiBle.startAudioError() ?? 'unknown'}`);
        return;
      }
      say('CCCD written (notify)');
      omiBle.onAudio(
        (bytes) => {
          setAudioChunks((c) => c + 1);
          setAudioBytes((b) => b + bytes.length);
        },
        (e) => say(`audio error: ${e instanceof Error ? e.message : String(e)}`)
      );
      setListening(true);
      say(`subscribed, codec ${identity?.codec ?? '?'} @ ${SAMPLE_RATE} Hz`);
    } catch (e) {
      say(`startAudio failed: ${String(e)}`);
    }
  }, [say, identity]);

  const stopAudio = useCallback(() => {
    omiBle.stopAudio();
    setListening(false);
    say('audio stopped');
  }, [say]);

  if (!DEV_LOCAL_BRAIN) {
    return (
      <View style={[styles.root, { backgroundColor: theme.background, paddingTop: insets.top + 40 }]}>
        <Text style={[styles.h1, { color: theme.text }]}>Dev screen disabled</Text>
        <Text style={[styles.note, { color: theme.textSecondary }]}>
          Restart Metro with EXPO_PUBLIC_DEV_LOCAL_BRAIN=1.
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.root, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + Spacing.three, paddingBottom: 40 }}>
        <Text style={[styles.h1, { color: theme.text }]}>omi device</Text>
        <Text style={[styles.note, { color: theme.textSecondary }]}>
          adapter: {bleState} · service {OMI.service.slice(0, 8)}…
        </Text>

        <View style={styles.pad}>
          <Btn label={scanning ? 'scanning…' : 'Scan (10s)'} onPress={scan} bg="#2563eb" disabled={scanning} />
          <Text style={[styles.label, { color: theme.textSecondary }]}>FOUND</Text>
          {found.length === 0 ? (
            <Text style={[styles.dim, { color: theme.textSecondary }]}>nothing yet</Text>
          ) : (
            found.map((d) => (
              <TouchableOpacity
                key={d.id}
                style={[styles.chip, { backgroundColor: theme.backgroundElement }]}
                onPress={() => connect(d.id)}
              >
                <Text style={[styles.chipText, { color: theme.text }]}>
                  {d.name ?? '(unnamed)'} · {d.rssi ?? '?'} dBm
                </Text>
                <Text style={[styles.dim, { color: theme.textSecondary }]}>{d.id}</Text>
              </TouchableOpacity>
            ))
          )}

          {identity && (
            <>
              <Text style={[styles.label, { color: theme.textSecondary }]}>IDENTITY</Text>
              {Object.entries(identity).map(([k, v]) => (
                <Text key={k} style={[styles.line, { color: theme.text }]}>
                  {k}: {String(v ?? '—')}
                </Text>
              ))}
            </>
          )}

          <Text style={[styles.label, { color: theme.textSecondary }]}>AUDIO</Text>
          <Text style={[styles.line, { color: theme.text }]}>
            chunks: {audioChunks} · bytes: {audioBytes}
            {listening ? ' · listening' : ''}
          </Text>
          <View style={styles.row}>
            <Btn label="Start audio" onPress={startAudio} bg="#16a34a" />
            <Btn label="Stop" onPress={stopAudio} bg="#444" />
          </View>

          <Text style={[styles.label, { color: theme.textSecondary }]}>TRANSCRIBE</Text>
          <Text style={[styles.line, { color: theme.text }]}>
            {capture.recording
              ? `streaming to STT · ${capture.segments.length} segments`
              : capture.connecting
                ? 'connecting…'
                : 'idle'}
          </Text>
          {capture.error ? (
            <Text style={[styles.err, { color: '#fca5a5' }]}>{capture.error}</Text>
          ) : null}
          <View style={styles.row}>
            <Btn
              label="Device -> STT"
              bg="#2563eb"
              disabled={capture.recording || capture.connecting || !identity}
              onPress={() => {
                if (!identity) return;
                capture.startFromOmi(identity.codec);
                say(`startFromOmi(${identity.codec})`);
              }}
            />
            <Btn
              label="Stop STT"
              bg="#444"
              disabled={!capture.recording}
              onPress={() => {
                capture.stop();
                say('capture.stop()');
              }}
            />
          </View>
          {capture.segments.length > 0 && (
            <>
              {capture.segments.slice(-6).map((sg, i) => (
                <Text key={i} style={[styles.line, { color: theme.text }]}>
                  {sg.speaker}: {sg.text}
                </Text>
              ))}
            </>
          )}

          <Text style={[styles.label, { color: theme.textSecondary }]}>LOG</Text>
          {log.length === 0 ? (
            <Text style={[styles.dim, { color: theme.textSecondary }]}>Scan first.</Text>
          ) : (
            log.map((l, i) => (
              <Text key={i} style={[styles.mono, { color: theme.text }]}>
                {l}
              </Text>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function Btn({ label, onPress, bg, disabled }: { label: string; onPress: () => void; bg: string; disabled?: boolean }) {
  return (
    <TouchableOpacity
      style={[styles.btn, { backgroundColor: bg }, disabled && styles.btnOff]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  h1: { fontSize: 24, fontWeight: '700', paddingHorizontal: Spacing.three },
  note: { fontSize: 12, paddingHorizontal: Spacing.three, marginBottom: Spacing.two },
  pad: { paddingHorizontal: Spacing.three, gap: Spacing.two },
  label: { fontSize: 11, marginTop: Spacing.three },
  btn: { paddingVertical: 13, borderRadius: 8, alignItems: 'center' },
  btnOff: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  chip: { padding: 11, borderRadius: 6, gap: 2 },
  chipText: { fontSize: 14, fontWeight: '600' },
  line: { fontSize: 13 },
  dim: { fontSize: 12 },
  mono: { fontSize: 11, fontFamily: 'monospace' },
  err: { fontSize: 12 },
  row: { flexDirection: 'row', gap: Spacing.two },
});