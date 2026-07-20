import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMemoriesStore } from '@/state/memoriesStore';
import { useConversationsStore } from '@/state/conversationsStore';
import type { Conversation, Memory } from '@/api/omiApi';

function dayLabel(iso?: string): string {
  if (!iso) return 'Unknown';
  const d = new Date(iso);
  const today = new Date();
  const y = new Date(today); y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === y.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function groupByDay(conversations: Conversation[]): { label: string; items: Conversation[] }[] {
  const map = new Map<string, Conversation[]>();
  for (const c of conversations) {
    const label = dayLabel(c.created_at);
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(c);
  }
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }));
}

function buildMindMap(memories: Memory[]): { tag: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of memories) {
    for (const t of m.tags ?? []) {
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);
}

export default function HomeScreen() {
  const memories = useMemoriesStore((s) => s.items);
  const conversations = useConversationsStore((s) => s.items);
  const loadMemories = useMemoriesStore((s) => s.load);
  const loadConversations = useConversationsStore((s) => s.load);
  const router = useRouter();
  const [query, setQuery] = useState('');

  useEffect(() => {
    loadMemories();
    loadConversations();
  }, [loadMemories, loadConversations]);

  const recaps = useMemo(() => groupByDay(conversations).slice(0, 5), [conversations]);
  const mindMap = useMemo(() => buildMindMap(memories), [memories]);

  return (
    <View style={styles.root}>
      <View style={styles.topBar}>
        <TouchableOpacity
          style={styles.connectBtn}
          onPress={() => router.push('/(tabs)/settings')}
          activeOpacity={0.8}
        >
          <Text style={styles.connectText}>Connect</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.recordBtn}
          onPress={() => router.push('/(tabs)/capture')}
          activeOpacity={0.8}
        >
          <Text style={styles.recordIcon}>●</Text>
          <Text style={styles.recordText}>Record</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <Text style={styles.sectionTitle}>Conversations</Text>
        {conversations.slice(0, 4).map((c) => (
          <TouchableOpacity
            key={c.id}
            style={styles.rowCard}
            onPress={() => router.push({ pathname: '/conversation/[id]', params: { id: c.id } })}
            activeOpacity={0.8}
          >
            <Text style={styles.rowTitle}>{c.title ?? c.id}</Text>
            <Text style={styles.rowSub}>{dayLabel(c.created_at)}</Text>
          </TouchableOpacity>
        ))}

        <Text style={styles.sectionTitle}>Daily Recaps</Text>
        {recaps.length === 0 && <Text style={styles.empty}>No recaps yet.</Text>}
        {recaps.map((r) => (
          <View key={r.label} style={styles.recapCard}>
            <Text style={styles.recapDay}>{r.label}</Text>
            {r.items.slice(0, 3).map((c) => (
              <Text key={c.id} style={styles.recapItem}>• {c.title ?? c.id}</Text>
            ))}
          </View>
        ))}

        <Text style={styles.sectionTitle}>Mind Map</Text>
        {mindMap.length === 0 && <Text style={styles.empty}>No tags yet.</Text>}
        <View style={styles.mindWrap}>
          {mindMap.map((m) => (
            <View key={m.tag} style={[styles.mindNode, { opacity: 0.5 + Math.min(m.count, 6) / 12 }]}>
              <Text style={styles.mindTag}>{m.tag}</Text>
              <Text style={styles.mindCount}>{m.count}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <View style={styles.inputBar}>
        <View style={styles.inputBox}>
          <TextInput
            style={styles.input}
            placeholder="Ask Omi anything about your life..."
            placeholderTextColor="#7A7A80"
            value={query}
            onChangeText={setQuery}
          />
          <TouchableOpacity style={styles.micBtn} activeOpacity={0.8}>
            <Text style={styles.micIcon}>🎙</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0B0B0F' },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 14, paddingBottom: 8,
  },
  recordBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#1C1C1E', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
  },
  recordIcon: { color: '#FF453A', fontSize: 12 },
  recordText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  connectBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#1C1C1E', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
  },
  connectText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 16, paddingBottom: 16 },
  sectionTitle: {
    fontSize: 18, fontWeight: '700', color: '#FFF', marginTop: 18, marginBottom: 8,
  },
  rowCard: {
    backgroundColor: '#1C1C1E', borderRadius: 12, padding: 12, marginBottom: 8,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  rowTitle: { color: '#FFF', fontSize: 15, flex: 1 },
  rowSub: { color: '#8E8E93', fontSize: 12 },
  recapCard: {
    backgroundColor: '#15151A', borderRadius: 12, padding: 12, marginBottom: 8,
  },
  recapDay: { color: '#0A84FF', fontSize: 14, fontWeight: '600', marginBottom: 4 },
  recapItem: { color: '#D0D0D6', fontSize: 13, paddingVertical: 2 },
  empty: { color: '#6A6A70', fontSize: 13, marginBottom: 8 },
  mindWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  mindNode: {
    backgroundColor: '#1C1C1E', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8,
    borderWidth: 1, borderColor: '#2A2A30',
  },
  mindTag: { color: '#FFF', fontSize: 13, fontWeight: '600' },
  mindCount: { color: '#8E8E93', fontSize: 11 },
  inputBar: {
    paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#0B0B0F',
    borderTopWidth: 1, borderTopColor: '#1C1C1E',
  },
  inputBox: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#1C1C1E', borderRadius: 24, paddingHorizontal: 16, paddingVertical: 4,
  },
  input: { flex: 1, color: '#FFF', fontSize: 15, paddingVertical: 10 },
  micBtn: {
    width: 36, height: 36, borderRadius: 18, backgroundColor: '#0A84FF',
    alignItems: 'center', justifyContent: 'center',
  },
  micIcon: { fontSize: 16 },
});
