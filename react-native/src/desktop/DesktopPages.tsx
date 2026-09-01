import React from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import CalendarDays from 'lucide-react-native/icons/calendar-days';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Sparkles from 'lucide-react-native/icons/sparkles';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import {ShippingListInsert} from './ShippingStage';
import {ConversationRow, EmptyCopy, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

export function LibraryPage({
  outcomes,
}: {
  outcomes: DesktopReadOutcomes | null;
}) {
  const conversations =
    outcomes?.conversations.status === 'success'
      ? outcomes.conversations.value.items
      : [];
  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {conversations.length > 0 ? (
          conversations.map(item => (
            <ShippingListInsert itemKey={item.id} key={item.id}>
              <ConversationRow item={item} />
            </ShippingListInsert>
          ))
        ) : (
          <EmptyCopy>Nothing captured in this window yet.</EmptyCopy>
        )}
      </ScrollView>
    </View>
  );
}

export function TasksPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {tasks.length > 0 ? (
          tasks.map(item => (
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
