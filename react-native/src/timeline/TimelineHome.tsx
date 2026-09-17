import {FocusPressable as Pressable} from '../ui/Pressable';
import React, {memo, useMemo} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import Check from 'lucide-react-native/icons/check';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Monitor from 'lucide-react-native/icons/monitor';
import Pencil from 'lucide-react-native/icons/pencil';
import {conversationGroupLabel} from '../desktopReadClient';
import {
  filterMixedTimeline,
  groupMixedTimeline,
  mergeMixedTimeline,
  type MixedTimelineItem,
  type TimelineConversation,
  type TimelineRecall,
} from './mixedTimeline';
import {
  mobileColor,
  mobileRadius,
  mobileSpace,
  mobileType,
} from '../mobile/mobileTokens';

export type TimelineTask = {
  id: string;
  title: string;
  completed: boolean;
};

export type TimelineProjectionStatus =
  | 'ready'
  | 'loading'
  | 'empty'
  | 'offline'
  | 'error';

export function TimelineStatePanel({
  status,
  noun,
}: {
  status: Exclude<TimelineProjectionStatus, 'ready'>;
  noun: string;
}) {
  const copy = {
    loading: `Loading ${noun}…`,
    empty:
      noun === 'action items'
        ? "Nothing's waiting on you."
        : noun === 'timeline'
        ? 'Nothing on your timeline yet.'
        : `No ${noun} yet`,
    offline: `Couldn’t refresh ${noun}`,
    error: `Couldn’t load ${noun}`,
  }[status];
  return (
    <View
      accessibilityLabel={`${noun} ${status} state`}
      accessibilityRole={
        status === 'error' || status === 'offline' ? 'alert' : undefined
      }
      style={styles.statePanel}>
      <Text style={styles.stateText}>{copy}</Text>
    </View>
  );
}

function TimelineRail({
  last,
  marker,
}: {
  last?: boolean;
  marker: React.ReactNode;
}) {
  return (
    <View style={styles.rail} pointerEvents="box-none">
      <View style={styles.marker}>{marker}</View>
      {last ? null : <View style={styles.line} />}
    </View>
  );
}

export const TimelineTaskRow = memo(function TimelineTaskRow({
  task,
  onToggle,
  onEdit,
  busy,
  last = false,
}: {
  task: TimelineTask;
  onToggle?: (id: string) => void;
  onEdit?: (id: string) => void;
  busy: boolean;
  last?: boolean;
}) {
  return (
    <View style={styles.taskRow}>
      <TimelineRail
        last={last}
        marker={
          <View style={[styles.checkbox, task.completed && styles.checkboxDone]}>
            {task.completed && (
              <Check color={mobileColor.background} size={12} />
            )}
          </View>
        }
      />
      <Pressable
        accessibilityLabel={`${
          onToggle
            ? task.completed
              ? 'Reopen'
              : 'Complete'
            : task.completed
            ? 'Completed'
            : 'Open'
        } ${task.title}`}
        accessibilityRole={onToggle ? 'checkbox' : 'text'}
        accessibilityState={{
          checked: task.completed,
          disabled: !onToggle || busy,
          busy,
        }}
        disabled={!onToggle || busy}
        onPress={() => onToggle?.(task.id)}
        style={styles.taskToggle}>
        <Text style={[styles.taskText, task.completed && styles.taskTextDone]}>
          {task.title}
        </Text>
      </Pressable>
      {onEdit && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Edit ${task.title}`}
          disabled={busy}
          onPress={() => onEdit(task.id)}
          style={styles.taskEdit}>
          <Pencil color={mobileColor.textMuted} size={16} />
        </Pressable>
      )}
    </View>
  );
});

function timeLabel(atMs: number | null): string {
  if (atMs === null || !Number.isFinite(atMs)) {
    return '';
  }
  return new Date(atMs).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export const TimelineEventRow = memo(function TimelineEventRow({
  item,
  onPress,
  last = false,
}: {
  item: MixedTimelineItem;
  onPress?: (item: MixedTimelineItem) => void;
  last?: boolean;
}) {
  const kind = item.kind === 'conversation' ? 'Conversation' : 'Recall';
  const title =
    item.kind === 'conversation'
      ? item.title || 'Conversation title unavailable'
      : item.appName;
  const detail =
    item.kind === 'conversation' ? item.summary : item.windowTitle;
  const Icon = item.kind === 'conversation' ? MessageCircle : Monitor;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Open ${kind} ${title}`}
      disabled={onPress === undefined}
      onPress={() => onPress?.(item)}
      style={styles.eventRow}>
      <TimelineRail
        last={last}
        marker={<Icon color={mobileColor.textMuted} size={14} />}
      />
      <View style={styles.eventBody}>
        <View style={styles.eventMeta}>
          <Text style={styles.kind}>{kind}</Text>
          <Text style={styles.time}>{timeLabel(item.atMs)}</Text>
        </View>
        <Text numberOfLines={2} style={styles.eventTitle}>
          {title}
        </Text>
        {detail ? (
          <Text numberOfLines={2} style={styles.eventDetail}>
            {detail}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
});

export function buildTimelineItems(input: {
  conversations: readonly TimelineConversation[];
  recall: readonly TimelineRecall[];
  query: string;
}): MixedTimelineItem[] {
  return filterMixedTimeline(
    mergeMixedTimeline({
      conversations: input.conversations,
      recall: input.recall,
    }),
    input.query,
  );
}

export function TimelineSections({
  items,
  nowEpochMilliseconds,
  onOpenItem,
  status,
}: {
  items: readonly MixedTimelineItem[];
  nowEpochMilliseconds: number;
  onOpenItem?: (item: MixedTimelineItem) => void;
  status: TimelineProjectionStatus;
}) {
  const groups = useMemo(
    () =>
      groupMixedTimeline(items, nowEpochMilliseconds, conversationGroupLabel),
    [items, nowEpochMilliseconds],
  );
  if (status !== 'ready') {
    return <TimelineStatePanel noun="timeline" status={status} />;
  }
  if (items.length === 0) {
    return <TimelineStatePanel noun="timeline" status="empty" />;
  }
  return (
    <View style={styles.timeline}>
      {groups.map(group => (
        <View key={group.label} style={styles.day}>
          <Text style={styles.dayLabel}>{group.label}</Text>
          {group.items.map((item, index) => (
            <TimelineEventRow
              key={`${item.kind}:${item.id}`}
              item={item}
              last={index === group.items.length - 1}
              onPress={onOpenItem}
            />
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  statePanel: {
    alignItems: 'center',
    backgroundColor: mobileColor.surface,
    borderRadius: mobileRadius.md,
    minHeight: 56,
    justifyContent: 'center',
    padding: mobileSpace.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: mobileColor.border,
  },
  stateText: {
    ...mobileType.body,
    color: mobileColor.textMuted,
    textAlign: 'center',
  },
  rail: {
    alignItems: 'center',
    alignSelf: 'stretch',
    width: 22,
  },
  marker: {
    alignItems: 'center',
    height: 22,
    justifyContent: 'center',
    marginTop: 10,
    width: 22,
    zIndex: 1,
  },
  line: {
    backgroundColor: mobileColor.border,
    flex: 1,
    width: StyleSheet.hairlineWidth,
  },
  taskRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    minHeight: 44,
    paddingBottom: 4,
  },
  taskToggle: {
    flex: 1,
    minHeight: 44,
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
  },
  taskEdit: {
    minHeight: 44,
    minWidth: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkbox: {
    borderColor: mobileColor.textSubtle,
    borderRadius: mobileRadius.round,
    borderWidth: 1.5,
    height: 18,
    width: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxDone: {backgroundColor: mobileColor.textSubtle},
  taskText: {fontSize: 15, lineHeight: 22, color: mobileColor.text, flex: 1},
  taskTextDone: {
    color: mobileColor.textSubtle,
    textDecorationLine: 'line-through',
  },
  timeline: {gap: 12},
  day: {gap: 6},
  dayLabel: {
    ...mobileType.caption,
    color: mobileColor.textMuted,
    paddingHorizontal: 2,
  },
  eventRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    minHeight: 52,
    paddingBottom: 14,
  },
  eventBody: {flex: 1, gap: 4, minWidth: 0},
  eventMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: mobileSpace.sm,
  },
  kind: {...mobileType.caption, color: mobileColor.textMuted},
  time: {...mobileType.caption, color: mobileColor.textSubtle},
  eventTitle: {...mobileType.body, color: mobileColor.text},
  eventDetail: {...mobileType.caption, color: mobileColor.textMuted},
});
