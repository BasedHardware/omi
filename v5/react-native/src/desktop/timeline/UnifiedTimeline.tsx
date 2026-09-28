import React from 'react';
import {ScrollView, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../../ui/MaterialIcon';
import {FocusPressable} from '../../ui/Pressable';
import {OmiPageState, OmiRow} from '../../design/primitives';
import {useOmiStyles, useOmiTheme} from '../../design/OmiTheme';
import type {OmiTheme} from '../../design/tokens';

import type {
  DesktopReadOutcomes,
  ConversationProjection,
  MemoryProjection,
  TaskProjection,
} from '../../desktopReadClient';
import {type ActivityFilterId, type TimelineGrouping} from '../desktopChrome';

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

function emptyTitle(filter: ActivityFilterId): string {
  switch (filter) {
    case 'conversations':
      return 'No Conversations Yet';
    case 'recall':
      return 'No Screen History Yet';
    case 'tasks':
      return 'No Tasks Yet';
    default:
      return 'Nothing Here Yet';
  }
}

/**
 * Unified activity timeline: one chronological feed of conversations,
 * memories, tasks, and recall capture groups — like the mobile app's day view.
 * The standalone Activity page owns the filters; this renders the merged feed
 * in a centered list column. Every entry uses the same row shape (OmiRow:
 * leading tile, title, subtitle, meta) and group headers are quiet labels.
 */
export function UnifiedTimeline({
  outcomes,
  query = '',
  loading,
  captures = [],
  filter = 'all',
  groupBy = 'date',
  onOpenEntry,
  onRetry,
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
  /** Retries a failed read; offered when nothing could be loaded at all. */
  onRetry?: () => void;
  /** Optional content rendered above the feed inside the scroll view. */
  header?: React.ReactNode;
}) {
  const styles = useOmiStyles(createStyles);
  const theme = useOmiTheme();
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
    const kind = kindMeta[entry.kind];
    const meta =
      entry.atMs === 0
        ? kind.label
        : `${kind.label} · ${timeLabel(entry.atMs)}`;
    // Memories are single-voice (title and summary carry the same sentence
    // from both backends), so the sentence is the title and there is no
    // subtitle — but the row keeps the same shape as every other entry.
    const subtitle =
      entry.kind === 'memory' || entry.detail.trim() === ''
        ? undefined
        : entry.detail;
    return (
      <OmiRow
        key={entry.id}
        accessibilityLabel={`${kind.label} ${entry.title}`}
        leadingIcon={kind.icon}
        meta={meta}
        onPress={onOpenEntry ? () => onOpenEntry(entry) : undefined}
        subtitle={subtitle}
        title={entry.title}
      />
    );
  };
  // Nothing could be read at all (no outcomes and not loading): say so and
  // offer Try Again. Failed reads never claim an empty timeline.
  const unavailable = outcomes === null && !loading;
  return (
    <View style={styles.root}>
      <ScrollView
        accessibilityLabel="Unified timeline"
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}>
        {header}
        {loading && entries.length === 0 ? (
          <OmiPageState kind="loading" label="Gathering your timeline…" />
        ) : unavailable ? (
          <OmiPageState
            kind="error"
            title="Couldn’t Load Your Activity"
            message="Some of your history isn't loaded yet."
            onRetry={onRetry}
          />
        ) : entries.length === 0 && failures.length === 0 ? (
          query.trim() !== '' ? (
            <OmiPageState
              kind="empty"
              icon="search"
              title="No Matches"
              message="Nothing in your timeline matches yet."
            />
          ) : (
            <OmiPageState
              kind="empty"
              icon={filter === 'all' ? 'view_timeline' : filterIcon[filter]}
              title={emptyTitle(filter)}
              message="Your timeline fills in as Omi captures your day."
            />
          )
        ) : null}
        {failures.length > 0 ? (
          <View accessibilityRole="alert" style={styles.failures}>
            <MaterialIcon
              name="info"
              size={theme.size.iconSmall}
              color={theme.color.danger}
            />
            <View style={styles.failureLines}>
              {failures.map(failure => (
                <Text key={failure} style={styles.failure}>
                  {failure}
                </Text>
              ))}
            </View>
          </View>
        ) : null}
        {sections.map(section => {
          const isCollapsed = collapsed.has(section.key);
          return (
            <View key={section.key}>
              <FocusPressable
                accessibilityLabel={`${isCollapsed ? 'Expand' : 'Collapse'} ${
                  section.label
                } section`}
                accessibilityRole="button"
                accessibilityState={{expanded: !isCollapsed}}
                style={state => [
                  styles.sectionHeader,
                  (state as {hovered?: boolean}).hovered &&
                    styles.sectionHeaderHovered,
                ]}
                onPress={() => toggleSection(section.key)}>
                <Text accessibilityRole="header" style={styles.sectionLabel}>
                  {section.label}
                </Text>
                <Text style={styles.sectionCount}>
                  {section.entries.length}
                </Text>
                <MaterialIcon
                  name="expand_more"
                  size={theme.size.iconSmall}
                  color={theme.color.inkSecondary}
                  style={isCollapsed ? styles.chevronClosed : undefined}
                />
              </FocusPressable>
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

const filterIcon: Record<ActivityFilterId, MaterialIconName> = {
  all: 'view_timeline',
  conversations: 'chat_bubble',
  recall: 'history',
  tasks: 'checklist',
};

const createStyles = (t: OmiTheme) => ({
  root: {flex: 1},
  // The feed reads as one centered list column; the chrome above keeps its
  // own width.
  content: {
    paddingHorizontal: t.layout.pageGutter.desktop,
    paddingBottom: t.space.xxl,
    maxWidth: t.layout.listColumn + 2 * t.layout.pageGutter.desktop,
    width: '100%' as const,
    alignSelf: 'center' as const,
  },
  sectionHeader: {
    alignItems: 'center' as const,
    borderRadius: t.radius.badge,
    flexDirection: 'row' as const,
    gap: t.space.xs + 2,
    marginTop: t.space.lg,
    marginBottom: t.space.xs,
    paddingLeft: t.space.sm,
    paddingRight: t.space.xs,
    paddingVertical: t.space.xs,
  },
  sectionHeaderHovered: {backgroundColor: t.color.fill},
  sectionLabel: {
    flex: 1,
    ...t.type.footnote,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  sectionCount: {
    ...t.type.caption,
    color: t.color.inkSecondary,
    fontVariant: ['tabular-nums' as const],
    fontWeight: '400' as const,
  },
  chevronClosed: {transform: [{rotate: '-90deg'}]},
  failures: {
    alignItems: 'flex-start' as const,
    backgroundColor: t.color.dangerSurface,
    borderRadius: t.radius.row,
    flexDirection: 'row' as const,
    gap: t.space.sm,
    marginTop: t.space.md,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.sm + 2,
  },
  failureLines: {flex: 1, gap: t.space.xxs},
  failure: {...t.type.subhead, color: t.color.danger},
});
