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
import {desktopTokens as token} from './tokens';

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

export function SectionTitle({children}: {children: string}) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

export function EmptyCopy({children}: {children: string}) {
  return <Text style={styles.emptyCopy}>{children}</Text>;
}

export const ReadRow = memo(function ReadRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
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
          {item.title}
        </Text>
        <Text numberOfLines={1} style={styles.rowMeta}>
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
  return (
    <View style={styles.row}>
      <RowGlyph kind="conversation" />
      <View style={styles.rowCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {item.title}
        </Text>
        <Text numberOfLines={1} style={styles.rowMeta}>
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

const styles = StyleSheet.create({
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    minHeight: 52,
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
    fontSize: token.type.title,
    fontWeight: '500',
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
  },
  sectionTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
    marginTop: 14,
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
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.body,
  },
  taskTextDone: {
    color: token.color.inkFaint,
    textDecorationLine: 'line-through',
  },
});
