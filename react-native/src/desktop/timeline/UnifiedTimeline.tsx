import React from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../../ui/MaterialIcon';
import {Pressable} from '../../ui/Pressable';

import type {
  DesktopReadOutcomes,
  ConversationProjection,
  MemoryProjection,
  TaskProjection,
} from '../../desktopReadClient';
import {OmiLoadingMark} from '../../ui/OmiLoadingMark';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from '../DesktopTheme';

type EntryKind = 'conversation' | 'memory' | 'task' | 'capture';

export type ActivityFilter = 'all' | 'conversations' | 'recall' | 'tasks';

export type TimelineEntry = {
  id: string;
  kind: EntryKind;
  atMs: number;
  title: string;
  detail: string;
};

export type CaptureGroupSummary = {
  id: string;
  title: string;
  appName: string;
  capturedAtMs: number;
  count: number;
};

function secondsOrMillisToMs(value: number): number {
  // Projections mix second and millisecond epochs; normalize to milliseconds.
  return value > 1e12 ? value : value * 1000;
}

function conversationEntry(item: ConversationProjection): TimelineEntry {
  const iso = item.finishedAt ?? item.startedAt ?? item.createdAt;
  const atMs = Date.parse(iso);
  return {
    id: `conversation-${item.id}`,
    kind: 'conversation',
    atMs: Number.isNaN(atMs) ? 0 : atMs,
    title: item.title.trim() !== '' ? item.title : 'Conversation',
    detail: item.summary,
  };
}

function memoryEntry(item: MemoryProjection): TimelineEntry {
  return {
    id: `memory-${item.id}`,
    kind: 'memory',
    atMs: item.timestamp === null ? 0 : secondsOrMillisToMs(item.timestamp),
    title: item.title.trim() !== '' ? item.title : 'Memory',
    detail: item.summary,
  };
}

function taskEntry(item: TaskProjection): TimelineEntry {
  const stamp = item.completedAt ?? item.dueAt;
  return {
    id: `task-${item.id}`,
    kind: 'task',
    atMs: stamp === null ? 0 : secondsOrMillisToMs(stamp),
    title: item.title.trim() !== '' ? item.title : 'Task',
    detail:
      item.completed && item.completedAt !== null
        ? `Done · ${item.summary}`
        : item.summary,
  };
}

function captureEntry(item: CaptureGroupSummary): TimelineEntry {
  return {
    id: `capture-${item.id}`,
    kind: 'capture',
    atMs: item.capturedAtMs,
    title: item.title,
    detail:
      item.count > 1
        ? `${item.appName} · ${item.count} captures`
        : item.appName,
  };
}

function entryFilterBucket(kind: EntryKind): ActivityFilter {
  if (kind === 'capture') {
    return 'recall';
  }
  if (kind === 'task') {
    return 'tasks';
  }
  return 'conversations';
}

function matchesQuery(entry: TimelineEntry, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === '') {
    return true;
  }
  return `${entry.title}\n${entry.detail}`.toLowerCase().includes(needle);
}

export function mergeTimeline(
  outcomes: DesktopReadOutcomes | null,
  query = '',
  captures: CaptureGroupSummary[] = [],
  filter: ActivityFilter = 'all',
): {entries: TimelineEntry[]; failures: string[]} {
  if (outcomes === null) {
    return {entries: [], failures: []};
  }
  const failures: string[] = [];
  const entries: TimelineEntry[] = [];
  if (outcomes.conversations.status === 'success') {
    for (const item of outcomes.conversations.value.items) {
      entries.push(conversationEntry(item));
    }
  } else {
    failures.push('Conversations are unavailable.');
  }
  if (outcomes.memories.status === 'success') {
    for (const item of outcomes.memories.value.items) {
      entries.push(memoryEntry(item));
    }
  } else {
    failures.push('Memories are unavailable.');
  }
  if (outcomes.tasks.status === 'success') {
    for (const item of outcomes.tasks.value.items) {
      entries.push(taskEntry(item));
    }
  } else {
    failures.push('Tasks are unavailable.');
  }
  for (const item of captures) {
    entries.push(captureEntry(item));
  }
  entries.sort((a, b) => b.atMs - a.atMs);
  return {
    entries: entries.filter(
      entry =>
        (filter === 'all' || entryFilterBucket(entry.kind) === filter) &&
        matchesQuery(entry, query),
    ),
    failures,
  };
}

function dayLabel(atMs: number): string {
  if (atMs === 0) {
    return 'Undated';
  }
  const day = new Date(atMs);
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const days = Math.round(
    (startOfToday.getTime() - day.getTime()) / (24 * 60 * 60 * 1000),
  );
  if (days <= 0) {
    return 'Today';
  }
  if (days === 1) {
    return 'Yesterday';
  }
  return day.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
}

function timeLabel(atMs: number): string {
  if (atMs === 0) {
    return '';
  }
  return new Date(atMs).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

const kindMeta: Record<EntryKind, {icon: MaterialIconName; label: string}> = {
  conversation: {icon: 'chat_bubble', label: 'Conversation'},
  memory: {icon: 'auto_awesome', label: 'Memory'},
  task: {icon: 'check_circle', label: 'Task'},
  capture: {icon: 'monitor', label: 'Recall'},
};

/**
 * Unified activity timeline: one chronological feed of conversations,
 * memories, tasks, and recall capture groups — like the mobile app's day view.
 * The standalone Activity page owns the filters; this renders the merged feed.
 */
export function UnifiedTimeline({
  outcomes,
  query = '',
  loading,
  captures = [],
  filter = 'all',
  onOpenEntry,
  header,
}: {
  outcomes: DesktopReadOutcomes | null;
  query?: string;
  loading: boolean;
  captures?: CaptureGroupSummary[];
  filter?: ActivityFilter;
  onOpenEntry?: (entry: TimelineEntry) => void;
  /** Optional content rendered above the feed inside the scroll view. */
  header?: React.ReactNode;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const {entries, failures} = mergeTimeline(outcomes, query, captures, filter);
  let lastDay = '';
  return (
    <View style={styles.root}>
      <ScrollView
        accessibilityLabel="Unified timeline"
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}>
        {header}
        {loading && entries.length === 0 ? (
          <View style={styles.loading}>
            <OmiLoadingMark inkColor={token.color.ink} size={56} />
            <Text style={styles.empty}>Gathering your timeline…</Text>
          </View>
        ) : entries.length === 0 && failures.length === 0 ? (
          <Text style={styles.empty}>
            {query.trim() !== ''
              ? 'Nothing in your timeline matches yet.'
              : 'Your timeline fills in as Omi captures your day.'}
          </Text>
        ) : null}
        {failures.map(failure => (
          <Text key={failure} style={styles.failure}>
            {failure}
          </Text>
        ))}
        {entries.map(entry => {
          const day = dayLabel(entry.atMs);
          const showDay = day !== lastDay;
          lastDay = day;
          const meta = kindMeta[entry.kind].icon;
          const body = (
            <View style={styles.row}>
              <View style={styles.rowIcon}>
                <MaterialIcon
                  name={meta}
                  size={16}
                  color={token.color.inkMuted}
                />
              </View>
              <View style={styles.rowBody}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {entry.title}
                </Text>
                {entry.detail.trim() !== '' ? (
                  <Text style={styles.rowDetail} numberOfLines={2}>
                    {entry.detail}
                  </Text>
                ) : null}
                <Text style={styles.rowMeta}>
                  {kindMeta[entry.kind].label}
                  {entry.atMs === 0 ? '' : ` · ${timeLabel(entry.atMs)}`}
                </Text>
              </View>
            </View>
          );
          return (
            <View key={entry.id}>
              {showDay ? <Text style={styles.day}>{day}</Text> : null}
              {onOpenEntry ? (
                <Pressable
                  accessibilityLabel={`${kindMeta[entry.kind].label} ${
                    entry.title
                  }`}
                  style={styles.rowPress}
                  onPress={() => onOpenEntry(entry)}>
                  {body}
                </Pressable>
              ) : (
                body
              )}
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    root: {flex: 1},
    content: {
      paddingHorizontal: 8,
      paddingBottom: 24,
      maxWidth: 860,
      width: '100%',
      alignSelf: 'center',
    },
    day: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 12,
      fontWeight: '600',
      letterSpacing: 0.4,
      marginTop: 22,
      marginBottom: 8,
      textTransform: 'uppercase',
    },
    row: {
      flexDirection: 'row',
      gap: 12,
      paddingVertical: 10,
      alignItems: 'flex-start',
    },
    rowPress: {
      borderRadius: 12,
      paddingHorizontal: 6,
      marginHorizontal: -6,
    },
    rowIcon: {
      width: 30,
      height: 30,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: token.color.glassQuiet,
    },
    rowBody: {flex: 1, minWidth: 0},
    rowTitle: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.body,
      fontWeight: '600',
    },
    rowDetail: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 13,
      lineHeight: 19,
      marginTop: 2,
    },
    rowMeta: {
      color: token.color.inkFaint,
      fontFamily: token.font,
      fontSize: 11,
      marginTop: 4,
    },
    empty: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: token.type.body,
      lineHeight: 22,
      paddingVertical: 32,
      textAlign: 'center',
    },
    loading: {
      alignItems: 'center',
      paddingTop: 24,
    },
    failure: {
      color: token.color.red,
      fontFamily: token.font,
      fontSize: 12,
      paddingBottom: 8,
      textAlign: 'center',
    },
  });
