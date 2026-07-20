import React, { useEffect, Component, type ReactNode } from 'react';
import { Stack } from 'expo-router';
import { Text, View, StyleSheet } from 'react-native';
import '../global.css';
import { useAuthStore } from '@/state/authStore';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    // Surface the error so a launch crash is visible instead of a black screen.
    console.error('App crashed:', error);
  }
  render() {
    if (this.state.error) {
      return (
        <View style={styles.container}>
          <Text style={styles.title}>App crashed on launch</Text>
          <Text style={styles.body}>{String(this.state.error?.message ?? this.state.error)}</Text>
          <Text style={styles.body}>{String(this.state.error?.stack ?? '').slice(0, 600)}</Text>
        </View>
      );
    }
    return this.props.children;
  }
}

export default function RootLayout() {
  const init = useAuthStore((s) => s.init);
  const uid = useAuthStore((s) => s.uid);
  useEffect(() => {
    try {
      init();
    } catch (e) {
      console.error('init failed', e);
    }
  }, [init]);

  return (
    <ErrorBoundary>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="conversation/[id]" />
        <Stack.Screen name="onboarding" />
      </Stack>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', padding: 24, justifyContent: 'center' },
  title: { color: '#ff6b6b', fontSize: 18, fontWeight: '700', marginBottom: 12 },
  body: { color: '#fff', fontSize: 12, fontFamily: 'monospace' },
});
