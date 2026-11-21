import React from 'react';
import { View, Text, Button, StyleSheet, Pressable } from 'react-native';
import { router } from 'expo-router';
import { useAuthStore } from '@/state/authStore';
import { DEV_LOCAL_BRAIN } from '@/devFlags';

/**
 * Developer tools, visible only in a dev build with the dev screens enabled.
 *
 * These are reachable by deep link, but a restored tab wins over an inbound link
 * often enough to be annoying -- so the links live in the UI as well. Gated on
 * DEV_LOCAL_BRAIN, which is __DEV__ plus an explicit env var; see devFlags.ts.
 */
function DevLinks() {
  if (!DEV_LOCAL_BRAIN) return null;
  return (
    <View style={styles.devBlock}>
      <Text style={styles.devHeading}>Developer</Text>
      <Pressable
        style={styles.devLink}
        onPress={() => router.push('/dev-local-brain')}
        testID="dev-link-local-brain"
      >
        <Text style={styles.devLinkText}>Local brain</Text>
      </Pressable>
      <Pressable
        style={styles.devLink}
        onPress={() => router.push('/dev-omi-device')}
        testID="dev-link-omi-device"
      >
        <Text style={styles.devLinkText}>omi device (BLE)</Text>
      </Pressable>
    </View>
  );
}

export default function SettingsScreen() {
  const { uid, logout } = useAuthStore();
  return (
    <View style={styles.container}>
      <Text style={styles.row}>Account: {uid ?? 'signed out'}</Text>
      <Button title="Sign out" onPress={() => logout()} />

      {/* Real features, always visible. The dev screens below are separate. */}
      <Pressable
        style={styles.navRow}
        onPress={() => router.push('/omi-device')}
        testID="settings-omi-device"
      >
        <Text style={styles.navText}>Wearable</Text>
        <Text style={styles.navChevron}>›</Text>
      </Pressable>
      <Pressable
        style={styles.navRow}
        onPress={() => router.push('/capture')}
        testID="settings-capture"
      >
        <Text style={styles.navText}>Record a conversation</Text>
        <Text style={styles.navChevron}>›</Text>
      </Pressable>
      <DevLinks />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, gap: 12 },
  row: { fontSize: 15 },
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
  },
  navText: { fontSize: 15, fontWeight: '600' },
  navChevron: { fontSize: 18, opacity: 0.5 },
  devBlock: { marginTop: 24, gap: 8 },
  devHeading: { fontSize: 12, opacity: 0.6, textTransform: 'uppercase' },
  devLink: { paddingVertical: 12, paddingHorizontal: 14, borderRadius: 8 },
  devLinkText: { fontSize: 15, fontWeight: '600' },
});