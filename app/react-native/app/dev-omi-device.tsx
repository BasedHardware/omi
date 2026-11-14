import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Pressable,
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  PermissionsAndroid,
  Platform,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';

import { useTheme } from '@/hooks/use-theme';
import { Spacing } from '@/constants/theme';
import { DEV_LOCAL_BRAIN } from '@/devFlags';
import { useCaptureStore } from '@/state/captureStore';
import { makeTonePcm, playPcm16Mono8k } from '@/services/omiSpeaker';
import { tts } from '@/services/tts';
import { useVoiceAgentStore, utteranceFrom } from '@/services/voiceAgent';
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
  const agent = useVoiceAgentStore();
  const transcriptRef = useRef<ScrollView>(null);
  const displaySegments = capture.segments.length > 0 ? capture.segments : capture.lastSegments;
  const liveWords = utteranceFrom(displaySegments);
  const interimPreview = displaySegments
    .filter((s) => !s.isFinal && s.text.trim())
    .map((s) => s.text.trim())
    .join(' ');

  useEffect(() => {
    if (displaySegments.length > 0) transcriptRef.current?.scrollToEnd({ animated: true });
  }, [displaySegments.length, capture.recording, interimPreview]);

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
      if (capture.recording || capture.connecting) {
        say('stop STT/capture before starting raw audio debug stream');
        return;
      }
      const enabled = await omiBle.startAudio();
      if (!enabled) {
        say(`CCCD write FAILED: ${omiBle.startAudioError() ?? 'unknown'}`);
        return;
      }
      say('subscribed via monitorCharacteristic (library writes the CCCD)');
      omiBle.onAudio(
        (bytes) => {
          setAudioChunks((c) => c + 1);
          setAudioBytes((b) => b + bytes.length);
        },
        (e) => {
          say(`audio error: ${e instanceof Error ? e.message : String(e)}`);
          setListening(false);
        }
      );
      setListening(true);
      say(`subscribed, codec ${identity?.codec ?? '?'} @ ${SAMPLE_RATE} Hz`);
    } catch (e) {
      setListening(false);
      say(`startAudio failed: ${String(e)}`);
    }
  }, [say, identity, capture.recording, capture.connecting]);

  const stopAudio = useCallback(() => {
    omiBle.stopAudio();
    setListening(false);
    say('audio stopped');
  }, [say]);

  const [speakerBusy, setSpeakerBusy] = useState(false);

  const playTone = useCallback(async () => {
    setSpeakerBusy(true);
    say('speaker: tone 660/880 Hz...');
    try {
      // Two 100 ms notes at 8 kHz = 3,200 mono bytes: one transmission, fits
      // even the pre-2.0.11 buffer. Verifies the BLE -> I2S -> MAX98357 path
      // end to end with no account, no network, no TTS dependency.
      const chirp = concatPcm([makeTonePcm(660, 100), makeTonePcm(880, 100)]);
      await playPcm16Mono8k(chirp, {
        onTransmission: (n, of) => say(`speaker: send ${n}/${of}`),
      });
      say('speaker: done - did it chirp?');
    } catch (e) {
      say(`speaker failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSpeakerBusy(false);
    }
  }, [say]);

  const speakOnDevice = useCallback(async () => {
    setSpeakerBusy(true);
    say('tts: synthesizing for device...');
    const ok = await tts.speakOnOmi('Hello from your Omi.');
    say(ok ? 'tts: played on device speaker' : 'tts: failed (signed in? backend honoring ulaw_8000?)');
    setSpeakerBusy(false);
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
        <View style={styles.backRow}>
          <Pressable
            style={styles.back}
            onPress={() => router.back()}
            accessibilityRole="button"
            accessibilityLabel="Back"
            testID="dev-back"
          >
            <Text style={[styles.backText, { color: theme.text }]}>‹ Back</Text>
          </Pressable>
          <Text style={[styles.h1, { color: theme.text }]}>omi device</Text>
        </View>
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
            {listening ? ' · raw listening' : ''}
          </Text>
          <Text style={[styles.dim, { color: theme.textSecondary }]}>
            Raw BLE audio counter only — don&apos;t run together with “Device → STT” / voice agent (they share the mic stream).
          </Text>
          <View style={styles.row}>
            <Btn
              label="Start audio"
              onPress={startAudio}
              bg="#16a34a"
              disabled={capture.recording || capture.connecting}
            />
            <Btn label="Stop" onPress={stopAudio} bg="#444" />
          </View>
          <Btn
            label={omiBle.connectedDeviceId ? 'Disconnect device' : 'Not connected'}
            bg="#b91c1c"
            disabled={!omiBle.connectedDeviceId}
            onPress={async () => {
              // Tear the capture down first: leaving the notification enabled
              // after a disconnect means the device pushes audio into a stream
              // that no longer has a socket.
              if (capture.recording) capture.stop();
              omiBle.stopAudio();
              await omiBle.disconnect();
              setIdentity(null);
              setAudioChunks(0);
              setAudioBytes(0);
              setListening(false);
              say('disconnected');
            }}
          />

          <Text style={[styles.label, { color: theme.textSecondary }]}>LIVE TRANSCRIPTION</Text>
          <Text style={[styles.line, { color: theme.text }]}>
            {capture.recording
              ? `listening (live) · ${capture.segments.length} segments`
              : capture.connecting
                ? 'connecting to STT…'
                : displaySegments.length > 0
                  ? `idle · last utterance captured`
                  : 'idle'}
          </Text>
          {capture.error ? (
            <Text style={[styles.err, { color: '#fca5a5' }]}>{capture.error}</Text>
          ) : null}
          {listening ? (
            <Text style={[styles.err, { color: '#fbbf24' }]}>
              Raw “Start audio” is on — stop it before Device → STT or it will steal the mic stream.
            </Text>
          ) : null}
          <View style={styles.row}>
            <Btn
              label="Device -> STT"
              bg="#2563eb"
              disabled={capture.recording || capture.connecting || !identity || listening}
              onPress={() => {
                if (!identity) return;
                if (listening) {
                  stopAudio();
                  setListening(false);
                }
                capture.startFromOmi(identity.codec);
                say(`startFromOmi(${identity.codec})`);
              }}
            />
            <Btn
              label="Stop STT"
              bg="#444"
              disabled={!capture.recording && !capture.connecting}
              onPress={() => {
                capture.stop();
                say('capture.stop()');
              }}
            />
          </View>
          <View style={styles.row}>
            <Btn
              label="Stop & ask agent"
              bg="#7c3aed"
              disabled={(!capture.recording && !capture.connecting && !liveWords) || !identity}
              onPress={() => {
                say('stop & ask agent');
                void agent.ask();
              }}
            />
          </View>
          <View style={[styles.transcriptBox, { backgroundColor: theme.backgroundElement, borderColor: theme.backgroundSelected }]}>
            <ScrollView
              ref={transcriptRef}
              nestedScrollEnabled
              style={styles.transcriptScroll}
              contentContainerStyle={styles.transcriptContent}
            >
              {displaySegments.length === 0 ? (
                <Text style={[styles.dim, { color: theme.textSecondary }]}>
                  {capture.recording || capture.connecting
                    ? 'Listening… speak now (words will appear live).'
                    : 'No transcript yet. Start “Device → STT” or attach button + double-tap.'}
                </Text>
              ) : (
                displaySegments.map((sg, i) => (
                  <Text
                    key={`${sg.start}-${i}-${sg.isFinal}`}
                    style={[
                      styles.line,
                      { color: theme.text },
                      !sg.isFinal ? { color: theme.textSecondary, fontStyle: 'italic' } : null,
                    ]}
                  >
                    {sg.isFinal ? '' : '… '}
                    {sg.speaker}: {sg.text}
                  </Text>
                ))
              )}
            </ScrollView>
          </View>
          {interimPreview ? (
            <Text style={[styles.dim, { color: theme.textSecondary, fontStyle: 'italic' }]}>
              hearing: {interimPreview}
            </Text>
          ) : null}
          {liveWords ? (
            <Text style={[styles.line, { color: theme.text }]}>
              will send to agent: &quot;{liveWords}&quot;
            </Text>
          ) : null}

          <Text style={[styles.label, { color: theme.textSecondary }]}>SPEAKER</Text>
          <Text style={[styles.dim, { color: theme.textSecondary }]}>
            BLE -&gt; I2S path. The tone needs no account; &ldquo;say hello&rdquo; needs sign-in
            and a backend serving ulaw_8000. Firmware before 2.0.11 plays clips as ~0.3 s
            bursts paced by a 4 s device-side sleep.
          </Text>
          <View style={styles.row}>
            <Btn
              label="Play tone"
              onPress={playTone}
              bg="#16a34a"
              disabled={speakerBusy || !identity}
            />
            <Btn
              label="Say hello"
              onPress={speakOnDevice}
              bg="#2563eb"
              disabled={speakerBusy || !identity}
            />
          </View>

          <Text style={[styles.label, { color: theme.textSecondary }]}>VOICE AGENT</Text>
          <Text style={[styles.dim, { color: theme.textSecondary }]}>
            Double-tap the device button to start talking; double-tap again to send.
            Reply is spoken on the device when the backend serves ulaw_8000, on the
            phone otherwise. Long press is power-off - avoid it while testing.
          </Text>
          <Text style={[styles.line, { color: theme.text }]}>
            {agent.status}
            {agent.lastReply ? ` - last: "${agent.lastReply}"` : ''}
          </Text>
          <View style={styles.row}>
            <Btn
              label={agent.attached ? 'Listener on' : 'Attach button'}
              onPress={() => void agent.attach()}
              bg="#16a34a"
              disabled={agent.attached || !identity}
            />
            <Btn label="Detach" onPress={() => agent.detach()} bg="#444" disabled={!agent.attached} />
          </View>

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

function concatPcm(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
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
  backRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.three, gap: Spacing.two },
  back: { paddingVertical: 6 },
  backText: { fontSize: 16, fontWeight: '600' },
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
  row: { flexDirection: 'row', gap: Spacing.two, flexWrap: 'wrap' },
  transcriptBox: { borderWidth: 1, borderRadius: 8, minHeight: 120, maxHeight: 220, overflow: 'hidden' },
  transcriptScroll: { flex: 1 },
  transcriptContent: { padding: 10, gap: 6 },
});