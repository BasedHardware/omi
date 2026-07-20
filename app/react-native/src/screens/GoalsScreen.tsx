import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, StyleSheet, ActivityIndicator } from 'react-native';
import { getActionItems, ActionItem } from '@/api/omiApi';

function group(items: ActionItem[]): { label: string; items: ActionItem[] }[] {
  const later: ActionItem[] = [];
  const none: ActionItem[] = [];
  const soon: ActionItem[] = [];
  for (const it of items) {
    if (it.due_date) soon.push(it);
    else if (it.priority && it.priority.toLowerCase() === 'later') later.push(it);
    else none.push(it);
  }
  return [
    { label: 'LATER', items: later },
    { label: 'NO DEADLINE', items: none },
    { label: 'UPCOMING', items: soon },
  ].filter((g) => g.items.length > 0);
}

export default function GoalsScreen() {
  const [items, setItems] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getActionItems()
      .then((res) => { if (active) setItems(res.data.results); })
      .catch(() => { if (active) setItems([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const groups = group(items);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#0A84FF" />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>No goals or tasks yet.</Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      data={groups}
      keyExtractor={(g) => g.label}
      renderItem={({ item }) => (
        <View style={styles.group}>
          <Text style={styles.groupTitle}>{item.label}</Text>
          {item.items.map((t) => (
            <View key={t.id} style={styles.task}>
              <Text style={styles.taskText}>{t.description}</Text>
            </View>
          ))}
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, backgroundColor: '#0B0B0F' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0B0B0F' },
  empty: { color: '#6A6A70', fontSize: 14 },
  group: { marginBottom: 18 },
  groupTitle: { color: '#8E8E93', fontSize: 12, fontWeight: '700', marginBottom: 8, letterSpacing: 1 },
  task: {
    backgroundColor: '#1C1C1E', borderRadius: 10, padding: 12, marginBottom: 8,
  },
  taskText: { color: '#FFF', fontSize: 14 },
});
