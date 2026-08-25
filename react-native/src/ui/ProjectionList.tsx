import React, {memo, useCallback} from 'react';
import {
  ActivityIndicator,
  FlatList,
  Text,
  View,
  type ViewProps,
} from 'react-native';
import type {DesktopReadProjection} from '../desktopReadClient';
import {styles} from './styles';

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
