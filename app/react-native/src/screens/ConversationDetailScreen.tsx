import React, { useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { useConversationsStore } from '@/state/conversationsStore';

interface Props {
  id: string;
}

export default function ConversationDetailScreen({ id }: Props) {
  const selected = useConversationsStore((s) => s.selected);
  const open = useConversationsStore((s) => s.open);
  useEffect(() => { open(id); }, [id, open]);

  const segments = selected?.transcript_segments ?? selected?.transcript ?? [];

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>{selected?.title ?? id}</Text>
      {segments.map((s, i) => (
        <Text key={i} style={styles.seg}>
          {s.speaker ?? (s.is_user ? 'You' : 'Other')}: {s.text}
        </Text>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  title: { fontSize: 20, fontWeight: '700', marginBottom: 12 },
  seg: { fontSize: 14, paddingVertical: 6 },
});
