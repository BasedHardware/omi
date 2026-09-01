import React, {useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import CalendarDays from 'lucide-react-native/icons/calendar-days';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Grid2X2 from 'lucide-react-native/icons/grid-2x2';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Sparkles from 'lucide-react-native/icons/sparkles';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import {TextInput} from 'react-native';
import {ShippingPressable} from './ShippingPressable';
import {ShippingListInsert} from './ShippingStage';
import {
  ConversationRow,
  EmptyCopy,
  MemoryRow,
  SectionTitle,
  TaskRow,
} from './DesktopRows';
import {RewindPanel} from './DesktopHome';
import {desktopTokens as token} from './tokens';

const libraryHubs = [
  'Activity',
  'Conversations',
  'Memories',
  'Rewind',
  'Brain Map',
] as const;

type LibraryHub = (typeof libraryHubs)[number];

function HubText({
  active,
  label,
  onPress,
}: {
  active: boolean;
  label: LibraryHub;
  onPress: () => void;
}) {
  return (
    <ShippingPressable
      accessibilityLabel={`Hub ${label}`}
      accessibilityRole="button"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={styles.hubItem}>
      <Text style={[styles.hubText, active && styles.hubTextActive]}>
        {label}
      </Text>
    </ShippingPressable>
  );
}

export function LibraryPage({
  outcomes,
}: {
  outcomes: DesktopReadOutcomes | null;
}) {
  const [hub, setHub] = useState<LibraryHub>('Activity');
  const conversations =
    outcomes?.conversations.status === 'success'
      ? outcomes.conversations.value.items
      : [];
  const memories =
    outcomes?.memories.status === 'success'
      ? outcomes.memories.value.items
      : [];
  const emptyCopy = 'Nothing captured in this window yet.';
  return (
    <View style={styles.page}>
      <View accessibilityRole="tablist" style={styles.hubRow}>
        {libraryHubs.map(label => (
          <HubText
            active={hub === label}
            key={label}
            label={label}
            onPress={() => setHub(label)}
          />
        ))}
      </View>
      {hub === 'Conversations' || hub === 'Activity' ? (
        <ScrollView contentContainerStyle={styles.listContent} style={styles.list}>
          {hub === 'Activity' ? <SectionTitle>Activity</SectionTitle> : null}
          {conversations.length > 0 ? (
            conversations.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <ConversationRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>{emptyCopy}</EmptyCopy>
          )}
        </ScrollView>
      ) : hub === 'Memories' ? (
        <ScrollView contentContainerStyle={styles.listContent} style={styles.list}>
          {memories.length > 0 ? (
            memories.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <MemoryRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>{emptyCopy}</EmptyCopy>
          )}
        </ScrollView>
      ) : hub === 'Rewind' ? (
        <RewindPanel />
      ) : (
        <View style={styles.centerState}>
          <Grid2X2 color={token.color.inkMuted} size={28} />
          <Text style={styles.emptyTitle}>No connections to show yet.</Text>
        </View>
      )}
    </View>
  );
}

export function TasksPage({
  outcomes,
}: {
  outcomes: DesktopReadOutcomes | null;
}) {
  const [query, setQuery] = useState('');
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
  const normalized = query.trim().toLocaleLowerCase();
  const visible = tasks.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  return (
    <View style={styles.page}>
      <View style={styles.tasksHeader}>
        <Text style={styles.pageTitle}>Tasks</Text>
        <View style={styles.searchControl}>
          <Search color={token.color.inkMuted} size={15} />
          <TextInput
            onChangeText={setQuery}
            placeholder="Search tasks…"
            placeholderTextColor={token.color.inkFaint}
            style={styles.searchInput}
            value={query}
          />
        </View>
      </View>
      <SectionTitle>Today</SectionTitle>
      <ScrollView contentContainerStyle={styles.listContent} style={styles.list}>
        {visible.length > 0 ? (
          visible.map(item => (
            <ShippingListInsert itemKey={item.id} key={item.id}>
              <TaskRow item={item} />
            </ShippingListInsert>
          ))
        ) : (
          <EmptyCopy>No tasks yet</EmptyCopy>
        )}
      </ScrollView>
    </View>
  );
}

const imports = [
  ['Calendar', 'Google Calendar', CalendarDays],
  ['Email', 'Gmail', Archive],
  ['Local files', 'This Mac', Folder],
  ['Apple Notes', 'Private notes', FileText],
  ['X (Twitter)', 'Your posts and bookmarks', Sparkles],
  ['ChatGPT', 'Memory import', Puzzle],
] as const;

export function AppsPage() {
  return (
    <View style={styles.page}>
      <Text style={styles.pageTitle}>Imports</Text>
      <ScrollView contentContainerStyle={styles.appGrid}>
        {imports.map(([name, source, Icon]) => (
          <View key={name} style={styles.appCard}>
            <View style={styles.appCardHeader}>
              <View style={styles.appIcon}>
                <Icon color={token.color.ink} size={18} />
              </View>
              <View>
                <Text style={styles.rowTitle}>{name}</Text>
                <Text style={styles.rowMeta}>{source}</Text>
              </View>
            </View>
            <Text style={styles.rowMeta}>Not connected</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1},
  hubRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    minHeight: 32,
  },
  hubItem: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
  },
  hubText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  hubTextActive: {color: token.color.ink},
  list: {flex: 1},
  listContent: {paddingBottom: 24, paddingTop: 4},
  pageTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '600',
  },
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  searchControl: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    height: 32,
  },
  searchInput: {
    color: token.color.ink,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.body,
    height: 32,
    minWidth: 0,
    paddingVertical: 0,
  },
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '500',
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
  },
  emptyTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    textAlign: 'center',
  },
  centerState: {
    alignItems: 'center',
    flex: 1,
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 40,
  },
  appGrid: {paddingTop: 10},
  appCard: {
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    flex: 1,
    margin: 6,
    minHeight: 104,
    padding: 12,
  },
  appCardHeader: {alignItems: 'center', flexDirection: 'row', gap: 10},
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 10,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
});
