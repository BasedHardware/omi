import React, { useCallback, useState } from 'react';
import { Pressable, View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';

import { LocalBrainBar, type RouteTrace } from '@/components/LocalBrainBar';
import { useTheme } from '@/hooks/use-theme';
import { Spacing } from '@/constants/theme';
import { DEV_LOCAL_BRAIN } from '@/devFlags';
import { routeWithProvider, ROUTE_PROTOTYPES, OUT_OF_DOMAIN_PROTOTYPES, type Route } from '@/services/localBrainRouter';
import { createNativeRouter, isLocalBrainAvailable, warmUp } from '../modules/local-brain';

/**
 * DEV-ONLY screen for looking at the local brain without signing in.
 *
 * Mounting LocalBrainBar from HomeScreen requires authentication, which makes the
 * one component that most needs a real screen hard to inspect. This screen is
 * reachable on its own, renders the same component, and also drives the router
 * directly so a decision can be made without going through the composer.
 *
 * Gated on DEV_LOCAL_BRAIN, which is false unless __DEV__ and the env var are both
 * set -- see src/devFlags.ts. With the flag off this renders nothing rather than
 * leaking a sign-in bypass into a release build.
 */

const SAMPLES = [
  'add a task: pay the electric bill',
  'put the electric bill on my list',
  'remind me to call the dentist at 4pm',
  'set a reminder to take out the bins tonight',
  'what is the weather',
  'how do i tie a knot',
];

export default function DevLocalBrainScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const [text, setText] = useState(SAMPLES[0] ?? '');
  const [trace, setTrace] = useState<RouteTrace | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadMs, setLoadMs] = useState<number | null>(null);

  // Named brainRouter, not router: `router` is the expo-router navigation
  // object imported above, and shadowing it broke the Back button.
  const brainRouter = React.useMemo(
    () =>
      isLocalBrainAvailable
        ? createNativeRouter(ROUTE_PROTOTYPES, OUT_OF_DOMAIN_PROTOTYPES)
        : null,
    []
  );

  const append = useCallback((line: string) => {
    setLog((prev) => [line, ...prev].slice(0, 12));
  }, []);

  const run = useCallback(async () => {
    if (!brainRouter) {
      append('no native router; the bar should say so');
      return;
    }
    setBusy(true);
    const t0 = Date.now();
    const outcome = await routeWithProvider(text, brainRouter);
    const ms = Date.now() - t0;
    setTrace({
      source: outcome.source,
      route: outcome.decision.kind === 'chat' ? 'chat' : (outcome.decision.kind as Route),
      margin: 'margin' in outcome ? outcome.margin : 0,
      reason: outcome.source === 'heuristic' ? outcome.reason : undefined,
    });
    append(`${ms}ms  ${JSON.stringify(outcome)}`);
    setBusy(false);
  }, [brainRouter, text, append]);

  const warm = useCallback(async () => {
    setBusy(true);
    const t0 = Date.now();
    const ok = await warmUp(ROUTE_PROTOTYPES, OUT_OF_DOMAIN_PROTOTYPES);
    setLoadMs(Date.now() - t0);
    append(`warmUp ${ok ? 'ok' : 'failed'} in ${Date.now() - t0}ms`);
    setBusy(false);
  }, [append]);

  if (!DEV_LOCAL_BRAIN) {
    return (
      <View style={[styles.root, { backgroundColor: theme.background, paddingTop: insets.top + 40 }]}>
        <Text style={[styles.gate, { color: theme.text }]}>Dev screen disabled.</Text>
        <Text style={[styles.gateNote, { color: theme.textSecondary }]}>
          Restart Metro with EXPO_PUBLIC_DEV_LOCAL_BRAIN=1 to enable it.
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.root, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + Spacing.three }}>
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
          <Text style={[styles.h1, { color: theme.text }]}>Local brain</Text>
        </View>
        <Text style={[styles.note, { color: theme.textSecondary }]}>
          native module: {String(isLocalBrainAvailable)} · warm-up:{' '}
          {loadMs == null ? 'not run' : `${loadMs}ms`}
        </Text>

        {/* The component under test, exactly as HomeScreen mounts it. */}
        <LocalBrainBar trace={trace} />

        <View style={styles.pad}>
          <Text style={[styles.label, { color: theme.textSecondary }]}>UTTERANCE</Text>
          <TextInput
            value={text}
            onChangeText={setText}
            style={[
              styles.input,
              { color: theme.text, backgroundColor: theme.backgroundElement },
            ]}
            placeholderTextColor={theme.textSecondary}
          />

          <View style={styles.row}>
            <TouchableOpacity
              style={[styles.btn, { backgroundColor: '#2563eb' }, busy && styles.btnDisabled]}
              onPress={run}
              disabled={busy}
            >
              <Text style={styles.btnText}>{busy ? 'routing...' : 'Route'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.btn, { backgroundColor: '#444' }, busy && styles.btnDisabled]}
              onPress={warm}
              disabled={busy}
            >
              <Text style={styles.btnText}>Warm up</Text>
            </TouchableOpacity>
          </View>

          <Text style={[styles.label, { color: theme.textSecondary }]}>SAMPLES</Text>
          <View style={styles.chips}>
            {SAMPLES.map((s) => (
              <TouchableOpacity
                key={s}
                style={[styles.chip, { backgroundColor: theme.backgroundElement }]}
                onPress={() => setText(s)}
              >
                <Text style={[styles.chipText, { color: theme.text }]}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.label, { color: theme.textSecondary }]}>LOG</Text>
          {log.length === 0 ? (
            <Text style={[styles.logLine, { color: theme.textSecondary }]}>
              Tap Route or Warm up.
            </Text>
          ) : (
            log.map((l, i) => (
              <Text key={i} style={[styles.logLine, { color: theme.text }]}>
                {l}
              </Text>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  backRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.three, gap: Spacing.two },
  back: { paddingVertical: 6 },
  backText: { fontSize: 16, fontWeight: '600' },
  pad: { paddingHorizontal: Spacing.three, gap: Spacing.two },
  h1: { fontSize: 24, fontWeight: '700', paddingHorizontal: Spacing.three },
  note: { fontSize: 12, paddingHorizontal: Spacing.three, marginBottom: Spacing.two },
  label: { fontSize: 11, marginTop: Spacing.three, marginBottom: Spacing.one },
  input: { padding: 12, borderRadius: 8, fontSize: 14 },
  row: { flexDirection: 'row', gap: Spacing.two },
  btn: { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  chips: { gap: Spacing.one },
  chip: { padding: 10, borderRadius: 6 },
  chipText: { fontSize: 13 },
  logLine: { fontSize: 11, fontFamily: 'monospace', marginBottom: Spacing.one },
  gate: { fontSize: 18, fontWeight: '600', textAlign: 'center' },
  gateNote: { fontSize: 12, textAlign: 'center', marginTop: 8 },
});