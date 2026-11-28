import React, { useState } from 'react';
import { View, Text, Button, StyleSheet, ScrollView, Pressable } from 'react-native';
import { WebView } from 'react-native-webview';
import { useCaptureStore } from '@/state/captureStore';

const SPEECHSIGN_URL = 'https://speechsign.vercel.app';

export default function CaptureScreen() {
  const { recording, connecting, error, segments, start, stop } = useCaptureStore();
  const [showSpeechSign, setShowSpeechSign] = useState(false);

  const label = connecting ? 'Connecting…' : recording ? 'Stop' : 'Start';
  const disabled = connecting;

  return (
    <View style={styles.container}>
      <View style={styles.controls}>
        <Button title={label} disabled={disabled} onPress={() => (recording ? stop() : start())} />
        <Pressable
          style={[styles.toggle, showSpeechSign ? styles.toggleOn : styles.toggleOff]}
          onPress={() => setShowSpeechSign((v) => !v)}
        >
          <Text style={styles.toggleText}>{showSpeechSign ? 'Hide SpeechSign' : 'Show SpeechSign'}</Text>
        </Pressable>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {showSpeechSign ? (
        <View style={styles.webviewContainer}>
          <Text style={styles.webviewLabel}>SpeechSign avatar (Omi transcripts → sign)</Text>
          <WebView
            source={{ uri: SPEECHSIGN_URL }}
            style={styles.webview}
            allowsInlineMediaPlayback
            mediaPlaybackRequiresUserAction={false}
            javaScriptEnabled
            domStorageEnabled
          />
        </View>
      ) : null}

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
  controls: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  toggle: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  toggleOn: { backgroundColor: '#1D4ED8' },
  toggleOff: { backgroundColor: '#374151' },
  toggleText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  error: { color: '#FF453A', fontSize: 13 },
  webviewContainer: { height: 320, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000' },
  webviewLabel: { color: '#9CA3AF', fontSize: 12, paddingHorizontal: 8, paddingVertical: 6, backgroundColor: '#111827' },
  webview: { flex: 1, backgroundColor: '#000' },
  transcript: { flex: 1, marginTop: 4 },
  seg: { fontSize: 14, paddingVertical: 4 },
});
