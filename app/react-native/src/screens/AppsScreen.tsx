import React from 'react';
import { View, Text, FlatList, StyleSheet, TouchableOpacity } from 'react-native';

const APPS = [
  { id: 'appointments', name: 'Appointments', desc: 'Sync your calendar and get reminders.' },
  { id: 'notion', name: 'Notion', desc: 'Push memories and summaries to Notion.' },
  { id: 'gmail', name: 'Gmail', desc: 'Summarize and draft emails with Omi.' },
  { id: 'github', name: 'GitHub', desc: 'Track issues and PRs from your conversations.' },
  { id: 'spotify', name: 'Spotify', desc: 'Control music with voice commands.' },
  { id: 'todoist', name: 'Todoist', desc: 'Turn conversations into actionable tasks.' },
];

export default function AppsScreen() {
  return (
    <FlatList
      style={styles.container}
      data={APPS}
      keyExtractor={(a) => a.id}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.card} activeOpacity={0.8}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.desc}>{item.desc}</Text>
          <Text style={styles.connect}>Connect</Text>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  card: {
    padding: 14, marginBottom: 12, backgroundColor: '#1C1C1E', borderRadius: 14,
  },
  name: { fontSize: 16, fontWeight: '600' },
  desc: { fontSize: 13, color: '#9A9AA0', marginTop: 4 },
  connect: { fontSize: 13, color: '#0A84FF', marginTop: 8, fontWeight: '600' },
});
