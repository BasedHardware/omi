import React, {memo, useCallback} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Text,
  View,
  type ViewProps,
} from 'react-native';
import {
  conversationCaptureCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationListUsesListenOverview,
  conversationRecapTitle,
  conversationHasFinishClock,
  formatConversationDuration,
  memoryCitationCopy,
  memoryDisplayTitle,
  memorySynthesisCopy,
  taskDisplaySummary,
  taskDisplayTitle,
  taskIndentPadding,
  projectionClockLabel,
  type DesktopReadProjection,
} from '../desktopReadClient';
import {styles} from './styles';

function displayTitle(item: DesktopReadProjection): string {
  if (item.kind === 'memory') {
    return memoryDisplayTitle(item);
  }
  if (item.kind === 'conversation') {
    return conversationListUsesListenOverview(item)
      ? conversationRecapTitle(item)
      : conversationDisplayTitle(item);
  }
  return taskDisplayTitle(item);
}

function displaySummary(item: DesktopReadProjection): string {
  if (item.kind === 'memory') {
    return memoryCitationCopy(item.citations);
  }
  if (item.kind === 'conversation') {
    return conversationDisplaySummary(item);
  }
  return taskDisplaySummary(item);
}

export const ProjectionRow = memo(function ProjectionRow({
  item,
  home = false,
  spine = false,
}: {
  item: DesktopReadProjection;
  home?: boolean;
  spine?: boolean;
}) {
  const conversation = item.kind === 'conversation' ? item : null;
  const listenOverview =
    conversation !== null && conversationListUsesListenOverview(conversation);
  const captureCopy =
    conversation !== null
      ? conversationCaptureCopy(conversation.capturedAtMs)
      : null;
  const synthesis = item.kind === 'memory' ? memorySynthesisCopy(item) : null;
  const indentPad =
    item.kind === 'task' ? taskIndentPadding(item.indentLevel) : 0;
  const rowPad = spine ? 18 : 16;
  return (
    <View
      style={[
        styles.resultRow,
        home && styles.homeCurrentRow,
        spine && styles.homeSpineRow,
        indentPad > 0 ? {paddingLeft: rowPad + indentPad} : null,
      ]}>
      {indentPad > 0 ? <View accessibilityLabel="Nested task" /> : null}
      <View style={styles.resultKindRow}>
        {home ? (
          <View style={styles.homeCurrentKindLead}>
            <View
              style={[
                styles.homeCurrentKindDot,
                item.kind === 'memory' && styles.homeCurrentKindDotMemory,
              ]}
            />
            <Text
              style={[
                styles.resultKind,
                styles.homeCurrentKind,
                spine && styles.homeSpineKind,
              ]}>
              {item.kind}
            </Text>
          </View>
        ) : (
          <Text style={[styles.resultKind, spine && styles.homeSpineKind]}>
            {item.kind}
          </Text>
        )}
        {item.kind === 'conversation' && item.starred && (
          <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
            Starred
          </Text>
        )}
        {item.kind === 'conversation' && item.locked ? (
          <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
            Locked
          </Text>
        ) : null}
        {item.kind === 'conversation' && item.discarded ? (
          <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
            Discarded
          </Text>
        ) : null}
        {item.kind === 'conversation' && item.status === 'failed' ? (
          <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
            Failed
          </Text>
        ) : null}
      </View>
      <Text
        numberOfLines={listenOverview ? 3 : 2}
        style={[
          styles.resultTitle,
          home && styles.homeCurrentTitle,
          spine && styles.homeSpineTitle,
        ]}>
        {displayTitle(item)}
      </Text>
      {listenOverview ? null : (
        <Text
          numberOfLines={2}
          style={[
            styles.resultSummary,
            home && styles.homeCurrentSummary,
            spine && styles.homeSpineSummary,
          ]}>
          {displaySummary(item)}
        </Text>
      )}
      {item.kind !== 'task' ? (
        <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
          {projectionClockLabel(item, Date.now())}
        </Text>
      ) : null}
      {captureCopy !== null ? (
        <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
          {captureCopy}
        </Text>
      ) : null}
      {synthesis !== null ? (
        <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
          {synthesis}
        </Text>
      ) : null}
      {conversation !== null && conversationHasFinishClock(conversation) ? (
        <Text style={[styles.resultMeta, spine && styles.homeSpineMeta]}>
          {formatConversationDuration(
            conversation.startedAt,
            conversation.finishedAt,
          )}
        </Text>
      ) : null}
    </View>
  );
});

export function ProjectionList({
  items,
  loading,
  error,
  emptyCopy,
  header,
  footer,
  emptyTitle,
  suppressEmpty,
  rowVariant = 'default',
  accessibilityLabel,
  style,
}: {
  items: DesktopReadProjection[];
  loading: boolean;
  error: string | null;
  emptyCopy: string;
  header?: React.ReactElement;
  footer?: React.ReactElement;
  emptyTitle?: string;
  suppressEmpty?: boolean;
  rowVariant?: 'default' | 'spine';
  accessibilityLabel?: string;
  style?: ViewProps['style'];
}) {
  const renderItem = useCallback(
    ({item}: {item: DesktopReadProjection}) => (
      <ProjectionRow item={item} spine={rowVariant === 'spine'} />
    ),
    [rowVariant],
  );
  const keyExtractor = useCallback(
    (item: DesktopReadProjection) => `${item.kind}:${item.id}`,
    [],
  );
  const spine = rowVariant === 'spine';
  const contentContainerStyle = spine
    ? styles.homeSpineList
    : styles.resultList;
  const empty = suppressEmpty ? null : loading ? (
    <View style={[styles.projectionEmpty, spine && styles.homeSpineEmpty]}>
      <ActivityIndicator color={spine ? '#505050' : '#888888'} />
      <Text
        style={[
          styles.projectionEmptyCopy,
          spine && styles.homeSpineEmptyCopy,
        ]}>
        Loading…
      </Text>
    </View>
  ) : (
    <View style={[styles.projectionEmpty, spine && styles.homeSpineEmpty]}>
      <Text
        style={[
          styles.projectionEmptyTitle,
          spine && styles.homeSpineEmptyTitle,
        ]}>
        {error === null
          ? emptyTitle ?? 'Nothing to show yet'
          : 'Unable to load'}
      </Text>
      <Text
        style={[
          styles.projectionEmptyCopy,
          spine && styles.homeSpineEmptyCopy,
        ]}>
        {error ?? emptyCopy}
      </Text>
    </View>
  );

  return (
    <FlatList
      accessibilityLabel={accessibilityLabel}
      contentContainerStyle={contentContainerStyle}
      data={items}
      keyExtractor={keyExtractor}
      ListEmptyComponent={empty}
      ListFooterComponent={footer ?? null}
      ListHeaderComponent={header ?? null}
      renderItem={renderItem}
      style={style}
    />
  );
}
