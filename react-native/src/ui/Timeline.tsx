import React, {useCallback, useMemo, useRef} from 'react';
import {ActivityIndicator, FlatList, Text, View} from 'react-native';
import {timelineGroups, type DesktopReadProjection} from '../desktopReadClient';
import {ProjectionRow} from './ProjectionList';
import {styles} from './styles';

export function HomeTimeline({
  emptyCopy,
  emptyTitle,
  footer,
  items,
  loading,
  recovery,
}: {
  emptyCopy: string;
  emptyTitle: string;
  footer: React.ReactElement;
  items: DesktopReadProjection[];
  loading: boolean;
  recovery?: React.ReactElement | null;
}) {
  const nowEpochMilliseconds = useRef(Date.now()).current;
  const groups = useMemo(
    () => timelineGroups(items, nowEpochMilliseconds),
    [items, nowEpochMilliseconds],
  );

  const timelineItems = useMemo(
    () =>
      groups.flatMap(group => [
        {group, item: null as DesktopReadProjection | null},
        ...group.items.map(item => ({group, item})),
      ]),
    [groups],
  );
  const renderItem = useCallback(
    ({item: {group, item}}: {item: (typeof timelineItems)[number]}) =>
      item === null ? (
        <View style={styles.macHomeDayHeading}>
          <View style={styles.macHomeSpineDot} />
          <Text accessibilityRole="header" style={styles.macHomeDayLabel}>
            {group.label}
          </Text>
        </View>
      ) : (
        <View style={styles.macHomeDayItems}>
          <ProjectionRow item={item} spine />
        </View>
      ),
    [],
  );
  const empty = loading ? (
    <View style={styles.macHomeInlineState}>
      <ActivityIndicator color="#777b77" />
      <Text style={styles.macHomeInlineCopy}>Loading timeline…</Text>
    </View>
  ) : recovery != null ? (
    recovery
  ) : (
    <View style={styles.macHomeInlineState}>
      <Text style={styles.macHomeInlineTitle}>{emptyTitle}</Text>
      <Text style={styles.macHomeInlineCopy}>{emptyCopy}</Text>
    </View>
  );
  return (
    <FlatList
      accessibilityLabel="Home chronological timeline"
      contentContainerStyle={styles.macHomeTimelineContent}
      data={timelineItems}
      keyExtractor={({group, item}) =>
        item === null ? `day:${group.label}` : `${item.kind}:${item.id}`
      }
      ListEmptyComponent={empty}
      ListFooterComponent={footer}
      renderItem={renderItem}
      style={styles.macHomeTimeline}
    />
  );
}
