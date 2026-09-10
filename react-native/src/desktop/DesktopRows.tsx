import React, {memo} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import CheckCircle2 from 'lucide-react-native/icons/circle-check';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Sparkles from 'lucide-react-native/icons/sparkles';
import {
  conversationCaptureCopy,
  conversationDiscardedPhotoCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationHasFinishClock,
  conversationListEmoji,
  conversationListStatusCopy,
  conversationListTag,
  conversationListUsesListenOverview,
  conversationRecapTitle,
  formatConversationDuration,
  formatTaskDue,
  memoryCitationCopy,
  memoryDisplayBody,
  memoryDisplayTitle,
  memoryLockedCopy,
  memoryLedgerSlotCopy,
  memoryLedgerPlaybookCopy,
  memoryBaselineCopy,
  memorySynthesisCopy,
  visibleDisplayText,
  projectionClockLabel,
  taskDisplayTitle,
  taskIndentPadding,
  type ConversationProjection,
  type DesktopReadProjection,
  type MemoryProjection,
  type TaskProjection,
} from '../desktopReadClient';
import {desktopTokens as token} from './tokens';

function timeLabel(item: DesktopReadProjection): string {
  return projectionClockLabel(item, Date.now());
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

function ConversationCopy({item}: {item: ConversationProjection}) {
  const listenOverview = conversationListUsesListenOverview(item);
  const captureCopy = conversationCaptureCopy(item.capturedAtMs);
  const emoji = conversationListEmoji(item);
  const photosCopy = conversationDiscardedPhotoCopy(item);
  const tag = conversationListTag(item);
  const listStatusCopy = conversationListStatusCopy(item.status);
  return (
    <View style={styles.rowCopy}>
      {emoji !== null ? <Text style={styles.rowTitle}>{emoji}</Text> : null}
      {tag !== null ? <Text style={styles.rowMeta}>{tag}</Text> : null}
      <Text numberOfLines={listenOverview ? 3 : 1} style={styles.rowTitle}>
        {listenOverview
          ? conversationRecapTitle(item)
          : conversationDisplayTitle(item)}
      </Text>
      {listenOverview ? null : (
        <Text numberOfLines={2} style={styles.rowSummary}>
          {conversationDisplaySummary(item)}
        </Text>
      )}
      <Text numberOfLines={1} style={styles.rowMeta}>
        {[timeLabel(item), item.starred ? 'Starred' : '']
          .filter(part => part !== '')
          .join(' · ')}
      </Text>
      {captureCopy !== null ? (
        <Text style={styles.rowMeta}>{captureCopy}</Text>
      ) : null}
      {item.locked || item.discarded || listStatusCopy !== null ? (
        <Text style={styles.rowMeta}>
          {[
            item.locked ? 'Locked' : '',
            item.discarded ? 'Discarded' : '',
            listStatusCopy ?? '',
          ]
            .filter(part => part !== '')
            .join(' · ')}
        </Text>
      ) : null}
      {photosCopy !== null ? (
        <Text style={styles.rowMeta}>{photosCopy}</Text>
      ) : null}
      {conversationHasFinishClock(item) ? (
        <Text style={styles.rowMeta}>
          {formatConversationDuration(item.startedAt, item.finishedAt)}
        </Text>
      ) : null}
    </View>
  );
}

export const ReadRow = memo(function ReadRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
  if (item.kind === 'conversation') {
    return (
      <View style={styles.row}>
        <RowGlyph kind="conversation" />
        <ConversationCopy item={item} />
      </View>
    );
  }
  const synthesis = item.kind === 'memory' ? memorySynthesisCopy(item) : null;
  const locked = item.kind === 'memory' ? memoryLockedCopy(item) : null;
  const ledgerSlot = item.kind === 'memory' ? memoryLedgerSlotCopy(item) : null;
  const ledgerPlaybook =
    item.kind === 'memory' ? memoryLedgerPlaybookCopy(item) : null;
  const baseline = item.kind === 'memory' ? memoryBaselineCopy(item) : null;
  const captureDevice =
    item.kind === 'memory'
      ? visibleDisplayText(item.captureDeviceLabel ?? '')
      : '';
  const meta =
    item.kind === 'memory'
      ? [timeLabel(item), memoryCitationCopy(item.citations)]
      : [timeLabel(item)];
  return (
    <View style={styles.row}>
      <RowGlyph kind={item.kind} />
      <View style={styles.rowCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {item.kind === 'memory'
            ? memoryDisplayTitle(item)
            : taskDisplayTitle(item)}
        </Text>
        <Text numberOfLines={1} style={styles.rowMeta}>
          {meta.filter(part => part !== '').join(' · ')}
        </Text>
        {locked !== null ? <Text style={styles.rowMeta}>{locked}</Text> : null}
        {ledgerSlot !== null ? (
          <Text style={styles.rowMeta}>{ledgerSlot}</Text>
        ) : null}
        {ledgerPlaybook !== null ? (
          <Text numberOfLines={3} style={styles.rowMeta}>
            {ledgerPlaybook}
          </Text>
        ) : null}
        {captureDevice !== '' ? (
          <Text style={styles.rowMeta}>{captureDevice}</Text>
        ) : null}
        {baseline !== null ? (
          <Text style={styles.rowMeta}>{baseline}</Text>
        ) : null}
        {synthesis !== null ? (
          <Text style={styles.rowMeta}>{synthesis}</Text>
        ) : null}
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
      <ConversationCopy item={item} />
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
        {memoryDisplayBody(item)}
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
  const indentPad = taskIndentPadding(item.indentLevel);
  return (
    <View
      style={[styles.taskRow, indentPad > 0 ? {paddingLeft: indentPad} : null]}>
      {indentPad > 0 ? (
        <View accessibilityLabel="Nested task" style={styles.taskIndentLead} />
      ) : null}
      <View
        style={[styles.taskCircle, item.completed && styles.taskCircleDone]}
      />
      <View style={styles.rowCopy}>
        <Text style={[styles.taskText, item.completed && styles.taskTextDone]}>
          {taskDisplayTitle(item)}
        </Text>
        <Text style={styles.rowMeta}>
          {item.completed
            ? `Completed · ${formatTaskDue(item.dueAt)}`
            : formatTaskDue(item.dueAt)}
        </Text>
        {item.exportCopy !== undefined ? (
          <Text style={styles.rowMeta}>{item.exportCopy}</Text>
        ) : null}
      </View>
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
  rowSummary: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
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
  taskIndentLead: {
    backgroundColor: token.color.inkMuted,
    borderRadius: 1,
    height: 20,
    width: 1.5,
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
