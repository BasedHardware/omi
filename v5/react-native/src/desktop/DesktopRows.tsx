import React, {memo} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';

import {
  projectionTimestamp,
  type ConversationProjection,
  type DesktopReadProjection,
  type MemoryProjection,
  type TaskProjection,
} from '../desktopReadClient';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

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

function RowGlyph({kind}: {kind: DesktopReadProjection['kind']}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const name =
    kind === 'conversation'
      ? 'chat_bubble'
      : kind === 'memory'
      ? 'auto_awesome'
      : 'check_circle';
  return (
    <View style={styles.glyph}>
      <MaterialIcon color={token.color.ink} name={name} size={16} />
    </View>
  );
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
  const styles = useDesktopStyleSheets(createStyles);
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

export function EmptyCopy({children}: {children: string}) {
  const styles = useDesktopStyleSheets(createStyles);
  return <Text style={styles.emptyCopy}>{children}</Text>;
}

export function PageHeading({
  title,
  subtitle,
  eyebrow,
}: {
  title: string;
  subtitle: string;
  eyebrow?: string;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.heading}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text accessibilityRole="header" style={styles.pageTitle}>
        {title}
      </Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
    </View>
  );
}

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

export const ReadRow = memo(function ReadRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const meta =
    item.kind === 'conversation'
      ? [timeLabel(item), item.summary]
      : item.kind === 'memory'
      ? [timeLabel(item), 'Memory']
      : [timeLabel(item)];
  return (
    <View style={styles.row}>
      <RowGlyph kind={item.kind} />
      <View style={styles.rowCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {item.kind === 'conversation' ? conversationTitle(item) : item.title}
        </Text>
        <Text numberOfLines={2} style={styles.rowMeta}>
          {meta.filter(part => part !== '').join(' · ')}
        </Text>
      </View>
    </View>
  );
});

export const ConversationRow = memo(function ConversationRow({
  item,
}: {
  item: ConversationProjection;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.row}>
      <RowGlyph kind="conversation" />
      <View style={styles.rowCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {conversationTitle(item)}
        </Text>
        <Text numberOfLines={2} style={styles.rowMeta}>
          {[timeLabel(item), item.summary]
            .filter(part => part !== '')
            .join(' · ')}
        </Text>
      </View>
    </View>
  );
});

export const MemoryRow = memo(function MemoryRow({
  item,
}: {
  item: MemoryProjection;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.memoryCard}>
      <Text numberOfLines={3} style={styles.memoryText}>
        {item.summary}
      </Text>
      <Text style={styles.rowMeta}>
        {item.timestamp === null
          ? 'Date unavailable'
          : new Date(item.timestamp * 1000).toLocaleDateString()}
      </Text>
    </View>
  );
});

export const TaskRow = memo(function TaskRow({item}: {item: TaskProjection}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.taskRow}>
      <View
        style={[styles.taskCircle, item.completed && styles.taskCircleDone]}
      />
      <Text style={[styles.taskText, item.completed && styles.taskTextDone]}>
        {item.title}
      </Text>
    </View>
  );
});

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    heading: {gap: 10, paddingBottom: 24},
    eyebrow: {
      fontSize: 10,
      letterSpacing: 1.4,
      fontWeight: '600',
      color: token.color.inkMuted,
    },
    pageTitle: {
      fontSize: 29,
      lineHeight: 36,
      letterSpacing: -0.9,
      fontWeight: '500',
      color: token.color.ink,
    },
    subtitle: {fontSize: 14, lineHeight: 22, color: token.color.inkMuted},
    row: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 10,
      minHeight: 64,
      paddingVertical: 8,
    },
    glyph: {
      alignItems: 'center',
      backgroundColor: token.color.glassQuiet,
      borderRadius: 12,
      height: 30,
      justifyContent: 'center',
      width: 30,
    },
    rowCopy: {flex: 1},
    rowTitle: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: 14,
      fontWeight: '500',
    },
    rowMeta: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: token.type.meta,
      lineHeight: 19,
      marginTop: 2,
    },
    sectionTitle: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: token.type.caption,
      fontWeight: '600',
      marginTop: 0,
    },
    emptyCopy: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: token.type.meta,
      lineHeight: 18,
      marginTop: 6,
    },
    memoryCard: {
      backgroundColor: token.color.glassQuiet,
      borderRadius: 16,
      marginBottom: 10,
      padding: 14,
    },
    memoryText: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.body,
      lineHeight: 20,
    },
    taskRow: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 12,
      minHeight: 44,
    },
    taskCircle: {
      borderColor: token.color.inkMuted,
      borderRadius: 11,
      borderWidth: 1.5,
      height: 22,
      width: 22,
    },
    taskCircleDone: {backgroundColor: token.color.ink},
    taskText: {
      flex: 1,
      lineHeight: 22,
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.body,
    },
    taskTextDone: {
      color: token.color.inkFaint,
      textDecorationLine: 'line-through',
    },
  });
