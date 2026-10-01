import React, {memo} from 'react';
import {Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';

import {
  projectionTimestamp,
  type ConversationProjection,
  type DesktopReadProjection,
  type TaskProjection,
} from '../desktopReadClient';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {OmiRow} from '../design/primitives';

function timeLabel(item: DesktopReadProjection): string {
  const timestamp = projectionTimestamp(item);
  if (timestamp === null || timestamp <= 0) {
    return '';
  }
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function conversationTitle(item: ConversationProjection): string {
  if (item.title !== '') {
    return item.title;
  }
  return item.status === 'processing'
    ? 'Processing conversation…'
    : 'Conversation title unavailable';
}

export function SectionTitle({children}: {children: string}) {
  const styles = useOmiStyles(createCopyStyles);
  return (
    <Text accessibilityRole="header" style={styles.sectionTitle}>
      {children}
    </Text>
  );
}

export function EmptyCopy({children}: {children: string}) {
  const styles = useOmiStyles(createCopyStyles);
  return <Text style={styles.emptyCopy}>{children}</Text>;
}

const createCopyStyles = (t: OmiTheme) => ({
  sectionTitle: {
    ...t.type.footnote,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  emptyCopy: {...t.type.subhead, color: t.color.inkSecondary},
});

/**
 * Whole-surface empty or error state in the OmiPageState shape: a glyph, a
 * title and one sentence on the page itself — never a filled, bordered slab.
 */
export function DesktopEmptyState({
  title,
  detail,
  icon = 'chat_bubble',
  error = false,
}: {
  title: string;
  detail: string;
  icon?: MaterialIconName;
  error?: boolean;
}) {
  const styles = useOmiStyles(createEmptyStyles);
  const theme = useOmiTheme();
  return (
    <View
      style={styles.emptyState}
      accessibilityRole={error ? 'alert' : undefined}>
      <MaterialIcon
        name={error ? 'info' : icon}
        size={28}
        color={theme.color.inkSecondary}
      />
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyDetail}>{detail}</Text>
    </View>
  );
}

const createEmptyStyles = (t: OmiTheme) => ({
  emptyState: {
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
    minHeight: 240,
    paddingVertical: t.space.section,
    paddingHorizontal: t.space.xxl,
  },
  emptyTitle: {
    ...t.type.headline,
    color: t.color.ink,
    textAlign: 'center' as const,
  },
  emptyDetail: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    textAlign: 'center' as const,
    maxWidth: 380,
  },
});

const rowIcon = (
  kind: DesktopReadProjection['kind'],
): 'chat_bubble' | 'auto_awesome' | 'check_circle' =>
  kind === 'conversation'
    ? 'chat_bubble'
    : kind === 'memory'
    ? 'auto_awesome'
    : 'check_circle';

/**
 * One row shape for every library entry (OmiRow: leading tile, title,
 * subtitle, meta). The caller owns pressing; rows are clear at rest.
 */
export const ReadRow = memo(function ReadRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
  if (item.kind === 'conversation') {
    return <ConversationRow item={item} />;
  }
  const time = timeLabel(item);
  const kind = item.kind === 'memory' ? 'Memory' : 'Task';
  return (
    <OmiRow
      leadingIcon={rowIcon(item.kind)}
      meta={time === '' ? kind : `${kind} · ${time}`}
      title={item.title}
    />
  );
});

export const ConversationRow = memo(function ConversationRow({
  item,
}: {
  item: ConversationProjection;
}) {
  const time = timeLabel(item);
  return (
    <OmiRow
      leadingIcon="chat_bubble"
      meta={time === '' ? 'Conversation' : `Conversation · ${time}`}
      subtitle={item.summary.trim() === '' ? undefined : item.summary}
      title={conversationTitle(item)}
    />
  );
});

export const TaskRow = memo(function TaskRow({item}: {item: TaskProjection}) {
  const styles = useOmiStyles(createTaskStyles);
  const theme = useOmiTheme();
  return (
    <View style={styles.taskRow}>
      <View
        style={[styles.taskCircle, item.completed && styles.taskCircleDone]}>
        {item.completed ? (
          <MaterialIcon name="check" size={12} color={theme.color.onInk} />
        ) : null}
      </View>
      <Text style={[styles.taskText, item.completed && styles.taskTextDone]}>
        {item.title}
      </Text>
    </View>
  );
});

const createTaskStyles = (t: OmiTheme) => ({
  taskRow: {
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    gap: t.space.md,
    minHeight: 40,
  },
  taskCircle: {
    alignItems: 'center' as const,
    borderColor: t.color.hairline,
    borderRadius: t.radius.pill,
    borderWidth: 1.5,
    height: 20,
    justifyContent: 'center' as const,
    width: 20,
  },
  taskCircleDone: {
    backgroundColor: t.color.inkSecondary,
    borderColor: 'transparent',
  },
  taskText: {flex: 1, ...t.type.body, color: t.color.ink},
  taskTextDone: {
    color: t.color.inkSecondary,
    textDecorationLine: 'line-through' as const,
  },
});
