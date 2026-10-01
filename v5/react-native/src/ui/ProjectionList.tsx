import React, {memo, useCallback} from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  View,
  type ViewProps,
} from 'react-native';
import type {DesktopReadProjection} from '../desktopReadClient';
import {styles} from './styles';
import {useOmiStyles} from '../design/OmiTheme';
import {OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {MobileRow} from '../mobile/MobileList';

const kindLabel = {
  conversation: 'Conversation',
  memory: 'Memory',
  task: 'Task',
} as const;

/** A search result in the Omi theme: grouped cell, one row shape. */
const ThemedRow = memo(function ThemedRow({
  item,
  first,
  last,
}: {
  item: DesktopReadProjection;
  first: boolean;
  last: boolean;
}) {
  const local = useOmiStyles(createThemedStyles);
  return (
    <View
      style={[local.cell, first && local.cellFirst, last && local.cellLast]}>
      {first ? null : <View style={local.separator} />}
      <MobileRow
        title={displayTitle(item)}
        subtitle={displaySummary(item) || null}
        meta={[
          kindLabel[item.kind],
          item.kind === 'conversation' && item.starred ? 'Starred' : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      />
    </View>
  );
});

function displayTitle(item: DesktopReadProjection): string {
  return item.kind === 'memory'
    ? item.title.replace(/^entity:[^\s]+\s+/, '')
    : item.title;
}

function displaySummary(item: DesktopReadProjection): string {
  return item.kind === 'memory'
    ? 'Synthesized memory with source citations'
    : item.summary;
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
  return (
    <View
      style={[
        styles.resultRow,
        home && styles.homeCurrentRow,
        spine && styles.homeSpineRow,
      ]}>
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
      </View>
      <Text
        numberOfLines={2}
        style={[
          styles.resultTitle,
          home && styles.homeCurrentTitle,
          spine && styles.homeSpineTitle,
        ]}>
        {displayTitle(item)}
      </Text>
      <Text
        numberOfLines={2}
        style={[
          styles.resultSummary,
          home && styles.homeCurrentSummary,
          spine && styles.homeSpineSummary,
        ]}>
        {displaySummary(item)}
      </Text>
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
  const local = useOmiStyles(createThemedStyles);
  const renderItem = useCallback(
    ({item, index}: {item: DesktopReadProjection; index: number}) =>
      rowVariant === 'spine' ? (
        <ProjectionRow item={item} spine />
      ) : (
        <ThemedRow
          item={item}
          first={index === 0}
          last={index === items.length - 1}
        />
      ),
    [rowVariant, items.length],
  );
  const keyExtractor = useCallback(
    (item: DesktopReadProjection) => `${item.kind}:${item.id}`,
    [],
  );
  const spine = rowVariant === 'spine';
  const contentContainerStyle = spine ? styles.homeSpineList : local.list;
  const empty = suppressEmpty ? null : !spine ? (
    loading ? (
      <OmiPageState kind="loading" label="Loading…" />
    ) : error !== null ? (
      <OmiPageState
        kind="error"
        title="Couldn’t Load Everything"
        message={error}
      />
    ) : (
      <OmiPageState
        kind="empty"
        icon="search"
        title={emptyTitle ?? 'Nothing to Show Yet'}
        message={emptyCopy}
      />
    )
  ) : loading ? (
    <View style={[styles.projectionEmpty, styles.homeSpineEmpty]}>
      <ActivityIndicator color="#505050" />
      <Text style={[styles.projectionEmptyCopy, styles.homeSpineEmptyCopy]}>
        Loading…
      </Text>
    </View>
  ) : (
    <View style={[styles.projectionEmpty, styles.homeSpineEmpty]}>
      <Text style={[styles.projectionEmptyTitle, styles.homeSpineEmptyTitle]}>
        {error === null
          ? emptyTitle ?? 'Nothing to show yet'
          : 'Unable to load'}
      </Text>
      <Text style={[styles.projectionEmptyCopy, styles.homeSpineEmptyCopy]}>
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

const createThemedStyles = (t: OmiTheme) => ({
  list: {
    flexGrow: 1,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.sm,
    paddingBottom: t.space.xxl,
  },
  cell: {backgroundColor: t.color.surface},
  cellFirst: {
    borderTopLeftRadius: t.radius.card,
    borderTopRightRadius: t.radius.card,
    overflow: 'hidden' as const,
  },
  cellLast: {
    borderBottomLeftRadius: t.radius.card,
    borderBottomRightRadius: t.radius.card,
    overflow: 'hidden' as const,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    marginLeft: t.space.lg,
    backgroundColor: t.color.separator,
  },
});
