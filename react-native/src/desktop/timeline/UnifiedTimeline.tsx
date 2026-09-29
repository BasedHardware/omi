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
import {type ActivityFilterId, type TimelineGrouping} from '../desktopChrome';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from '../DesktopTheme';

type EntryKind = 'conversation' | 'memory' | 'task' | 'capture';

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

function entryFilterBucket(kind: EntryKind): ActivityFilterId {
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
  filter: ActivityFilterId = 'all',
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

export type TimelineSection = {
  key: string;
  label: string;
  entries: TimelineEntry[];
};

function sectionForGrouping(
  entry: TimelineEntry,
  grouping: TimelineGrouping,
  topicOf: (entry: TimelineEntry) => string,
): string {
  if (grouping === 'type') {
    return kindMeta[entry.kind].label;
  }
  if (grouping === 'topic') {
    return topicOf(entry);
  }
  return dayLabel(entry.atMs);
}

const TOPIC_STOPWORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'that',
  'this',
  'from',
  'have',
  'has',
  'are',
  'was',
  'were',
  'will',
  'your',
  'about',
  'into',
  'over',
  'after',
  'before',
  'what',
  'when',
  'they',
  'them',
  'their',
  'there',
  'where',
  'which',
  'while',
  'would',
  'could',
  'should',
  'been',
  'being',
  'does',
  'done',
  'just',
  'like',
  'some',
  'more',
  'than',
  'then',
  'because',
  'also',
  'very',
  'much',
  'many',
  'most',
  'other',
  'such',
  'only',
  'both',
  'each',
  'once',
  'here',
  'how',
  'who',
  'whom',
  'its',
  'our',
  'you',
  'she',
  'him',
  'her',
  'his',
  'says',
  'said',
  'new',
  'now',
  'one',
  'two',
  'all',
  'can',
  'get',
  'got',
  'make',
  'made',
  'out',
  'up',
  'down',
  'not',
  'but',
  'yet',
  'off',
  'own',
  'same',
  'so',
  'too',
  'very',
  'sobre',
  'via',
  'using',
  'used',
  'use',
]);

function topicTokens(entry: TimelineEntry): string[] {
  const haystack = `${entry.title} ${entry.detail}`.toLowerCase();
  const matches = haystack.match(/[a-z][a-z0-9+#]*/g) ?? [];
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const token of matches) {
    if (token.length < 4 || TOPIC_STOPWORDS.has(token) || seen.has(token)) {
      continue;
    }
    seen.add(token);
    tokens.push(token);
  }
  return tokens;
}

const OTHER_TOPIC = 'Everything else';

/**
 * Groups entries into collapsible timeline sections. `date` buckets by day,
 * `type` by entry kind, and `topic` by the most-shared significant keyword —
 * entries that share no repeated keyword land in "Everything else" (last).
 */
export function groupTimelineSections(
  entries: TimelineEntry[],
  grouping: TimelineGrouping,
): TimelineSection[] {
  if (grouping === 'topic') {
    const frequency = new Map<string, number>();
    const entryTokens = new Map<string, string[]>();
    for (const entry of entries) {
      const tokens = topicTokens(entry);
      entryTokens.set(entry.id, tokens);
      for (const token of tokens) {
        frequency.set(token, (frequency.get(token) ?? 0) + 1);
      }
    }
    const topicOf = (entry: TimelineEntry): string => {
      const tokens = entryTokens.get(entry.id) ?? [];
      let best: string | null = null;
      let bestCount = 1;
      for (const token of tokens) {
        const count = frequency.get(token) ?? 0;
        if (count > bestCount) {
          best = token;
          bestCount = count;
        }
      }
      if (best === null) {
        return OTHER_TOPIC;
      }
      return best.charAt(0).toUpperCase() + best.slice(1);
    };
    const sections: TimelineSection[] = [];
    const other: TimelineEntry[] = [];
    for (const entry of entries) {
      const label = topicOf(entry);
      if (label === OTHER_TOPIC) {
        other.push(entry);
        continue;
      }
      let section = sections.find(item => item.label === label);
      if (section === undefined) {
        section = {key: `topic-${label}`, label, entries: []};
        sections.push(section);
      }
      section.entries.push(entry);
    }
    if (other.length > 0) {
      sections.push({key: 'topic-other', label: OTHER_TOPIC, entries: other});
    }
    return sections;
  }
  const sections: TimelineSection[] = [];
  for (const entry of entries) {
    const label = sectionForGrouping(entry, grouping, () => OTHER_TOPIC);
    let section = sections.find(item => item.label === label);
    if (section === undefined) {
      section = {
        key: `${grouping}-${label}`,
        label,
        entries: [],
      };
      sections.push(section);
    }
    section.entries.push(entry);
  }
  return sections;
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
  groupBy = 'date',
  onOpenEntry,
  header,
}: {
  outcomes: DesktopReadOutcomes | null;
  query?: string;
  loading: boolean;
  captures?: CaptureGroupSummary[];
  filter?: ActivityFilterId;
  /** How entries collapse into sections: by day, kind, or shared topic. */
  groupBy?: TimelineGrouping;
  onOpenEntry?: (entry: TimelineEntry) => void;
  /** Optional content rendered above the feed inside the scroll view. */
  header?: React.ReactNode;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const {entries, failures} = mergeTimeline(outcomes, query, captures, filter);
  const sections = React.useMemo(
    () => groupTimelineSections(entries, groupBy),
    [entries, groupBy],
  );
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());
  const toggleSection = (key: string) => {
    setCollapsed(previous => {
      const next = new Set(previous);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };
  const renderEntry = (entry: TimelineEntry): React.ReactNode => {
    const meta = kindMeta[entry.kind].icon;
    // Memories are single-voice like the mobile app's memory cards: the
    // sentence is the row (title and summary carry the same text from both
    // backends), so no boxed icon and no duplicated second text line.
    const body =
      entry.kind === 'memory' ? (
        <View style={styles.memoryRow}>
          <MaterialIcon
            name={meta}
            size={13}
            color={token.color.inkMuted}
            style={styles.memoryLeadingIcon}
          />
          <View style={styles.rowBody}>
            <Text style={styles.memoryText} numberOfLines={3}>
              {entry.title.trim() !== '' ? entry.title : 'Memory'}
            </Text>
            <Text style={styles.rowMeta}>
              {kindMeta[entry.kind].label}
              {entry.atMs === 0 ? '' : ` · ${timeLabel(entry.atMs)}`}
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.row}>
          <View style={styles.rowIcon}>
            <MaterialIcon name={meta} size={16} color={token.color.inkMuted} />
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
        {onOpenEntry ? (
          <Pressable
            accessibilityLabel={`${kindMeta[entry.kind].label} ${entry.title}`}
            style={({hovered, pressed}) => [
              styles.rowPress,
              hovered && !pressed && styles.rowHover,
              pressed && styles.rowPressed,
            ]}
            onPress={() => onOpenEntry(entry)}>
            {body}
          </Pressable>
        ) : (
          body
        )}
      </View>
    );
  };
  return (
    <View style={styles.root}>
      <ScrollView
        accessibilityLabel="Unified timeline"
        scrollEventThrottle={16}
        style={styles.scroller}
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
        {sections.map(section => {
          const isCollapsed = collapsed.has(section.key);
          return (
            <View key={section.key}>
              <Pressable
                accessibilityLabel={`${isCollapsed ? 'Expand' : 'Collapse'} ${
                  section.label
                } section`}
                accessibilityRole="button"
                style={({hovered, pressed}) => [
                  styles.sectionHeader,
                  hovered && !pressed && styles.sectionHeaderHover,
                  pressed && styles.pressed,
                ]}
                onPress={() => toggleSection(section.key)}>
                <MaterialIcon
                  name="expand_more"
                  size={16}
                  color={token.color.inkMuted}
                  style={isCollapsed ? styles.chevronClosed : undefined}
                />
                <Text style={styles.sectionLabel}>{section.label}</Text>
                <Text style={styles.sectionCount}>
                  {section.entries.length}
                </Text>
              </Pressable>
              {isCollapsed
                ? null
                : section.entries.map(entry => renderEntry(entry))}
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
    scroller: {
      // Full-width stretch: the omnibar and filter rows above no longer cap
      // at 992, so the timeline stretches with them on wide windows.
      alignSelf: 'center',
      width: '100%',
    },
    content: {
      paddingHorizontal: 8,
      paddingBottom: 24,
      width: '100%',
    },
    sectionHeader: {
      alignItems: 'center',
      backgroundColor: token.color.glassQuiet,
      borderColor: token.color.line,
      borderRadius: 10,
      borderWidth: 1,
      flexDirection: 'row',
      gap: 8,
      marginTop: 18,
      paddingHorizontal: 12,
      paddingVertical: 8,
    },
    sectionHeaderHover: {backgroundColor: token.color.glassStrong},
    pressed: {opacity: 0.78},
    sectionLabel: {
      color: token.color.ink,
      flex: 1,
      fontFamily: token.font,
      fontSize: 12,
      fontWeight: '600',
      letterSpacing: 0.4,
      textTransform: 'uppercase',
    },
    sectionCount: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 11,
      fontVariant: ['tabular-nums'],
    },
    chevronClosed: {transform: [{rotate: '-90deg'}]},
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
    rowHover: {backgroundColor: token.color.glassQuiet},
    rowPressed: {opacity: 0.78},
    rowIcon: {
      width: 30,
      height: 30,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: token.color.glassQuiet,
    },
    rowBody: {flex: 1, minWidth: 0},
    memoryRow: {
      alignItems: 'flex-start',
      flexDirection: 'row',
      gap: 8,
      paddingVertical: 10,
    },
    memoryLeadingIcon: {marginTop: 3},
    memoryText: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: 14,
      fontWeight: '400',
      lineHeight: 20,
    },
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
