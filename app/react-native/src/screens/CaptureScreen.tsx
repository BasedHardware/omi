import React from 'react';
import { View, Text, Button, StyleSheet, ScrollView } from 'react-native';
import { useCaptureStore } from '@/state/captureStore';

export default function CaptureScreen() {
  const { recording, connecting, error, segments, start, stop } = useCaptureStore();

  const label = connecting ? 'Connecting…' : recording ? 'Stop' : 'Start';
  const disabled = connecting;

  return (
    <View style={styles.container}>
      <Button title={label} disabled={disabled} onPress={() => (recording ? stop() : start())} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView style={styles.transcript}>
        {segments.map((s, i) => (
          <Text key={i} style={styles.seg}>
            {s.speaker}: {s.text}
          </Text>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, gap: 12 },
  error: { color: '#FF453A', fontSize: 13 },
  transcript: { flex: 1, marginTop: 8 },
  seg: { fontSize: 14, paddingVertical: 4 },
});
