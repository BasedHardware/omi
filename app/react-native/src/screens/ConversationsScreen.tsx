import React, { useEffect } from 'react';
import { View, Text, FlatList, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useConversationsStore } from '@/state/conversationsStore';
import { Card, EmptyState } from '@/ui/components';
import { OmiColors, OmiSpacing, OmiType } from '@/ui/tokens';

function formatDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function ConversationsScreen() {
  const items = useConversationsStore((s) => s.items);
  const load = useConversationsStore((s) => s.load);
  const router = useRouter();
  useEffect(() => { load(); }, [load]);

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>HISTORY</Text>
        <Text style={styles.title}>Conversations</Text>
        <Text style={styles.subtitle}>Browse what you’ve captured and revisit details.</Text>
      </View>
      <FlatList
        style={styles.list}
        contentContainerStyle={styles.content}
        data={items}
        keyExtractor={(c) => c.id}
        ListEmptyComponent={<EmptyState text="No conversations yet." />}
        renderItem={({ item }) => (
          <Card
            style={styles.card}
            onPress={() => router.push({ pathname: '/conversation/[id]', params: { id: item.id } })}
          >
            <View style={styles.row}>
              <View style={styles.main}>
                <Text style={styles.rowTitle} numberOfLines={1}>{item.title ?? item.id}</Text>
                <Text style={styles.rowSub}>{formatDate(item.created_at)}</Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </View>
          </Card>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: OmiColors.surface0 },
  header: {
    paddingHorizontal: OmiSpacing.lg,
    paddingTop: OmiSpacing.xxl + 8,
    paddingBottom: OmiSpacing.md,
  },
  eyebrow: {
    ...OmiType.caption,
    color: OmiColors.textTertiary,
    letterSpacing: 1.2,
    fontWeight: '600',
    marginBottom: 4,
  },
  title: { ...OmiType.title1, color: OmiColors.textPrimary, marginBottom: 4 },
  subtitle: { ...OmiType.subhead, color: OmiColors.textSecondary },
  list: { flex: 1 },
  content: { paddingHorizontal: OmiSpacing.lg, paddingBottom: OmiSpacing.xxl },
  card: { marginBottom: OmiSpacing.xs, paddingVertical: OmiSpacing.sm + 2 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  main: { flex: 1, paddingRight: OmiSpacing.sm },
  rowTitle: { ...OmiType.headline, color: OmiColors.textPrimary },
  rowSub: { ...OmiType.footnote, color: OmiColors.textTertiary, marginTop: 2 },
  chevron: { ...OmiType.title3, color: OmiColors.textDisabled },
});
