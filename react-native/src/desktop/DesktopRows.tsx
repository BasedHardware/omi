import React, {memo} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import CheckCircle2 from 'lucide-react-native/icons/circle-check';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Sparkles from 'lucide-react-native/icons/sparkles';
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
  const Icon =
    kind === 'conversation'
      ? MessageCircle
      : kind === 'memory'
      ? Sparkles
      : CheckCircle2;
  return (
    <View style={styles.glyph}>
      <Icon color={token.color.ink} size={16} />
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

export function DesktopEmptyState({
  title,
  detail,
  icon: Icon = MessageCircle,
  error = false,
}: {
  title: string;
  detail: string;
  icon?: typeof MessageCircle;
  error?: boolean;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  return (
    <View
      style={styles.emptyState}
      accessibilityRole={error ? 'alert' : undefined}>
      <View style={styles.emptyGlyph}>
        <Icon size={24} color={token.color.inkMuted} />
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyDetail}>{detail}</Text>
    </View>
  );
}

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
    emptyState: {
      alignItems: 'center',
      justifyContent: 'center',
      padding: 32,
      minHeight: 240,
      gap: 12,
      backgroundColor: token.color.glassStrong,
      borderWidth: 1,
      borderColor: token.color.line,
      borderRadius: 18,
    },
    emptyGlyph: {
      width: 52,
      height: 52,
      borderRadius: 18,
      backgroundColor: token.color.glassQuiet,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 6,
    },
    emptyTitle: {
      fontSize: 19,
      lineHeight: 26,
      color: token.color.ink,
      textAlign: 'center',
      fontWeight: '500',
    },
    emptyDetail: {
      fontSize: 13,
      lineHeight: 21,
      color: token.color.inkMuted,
      textAlign: 'center',
      maxWidth: 380,
    },
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
