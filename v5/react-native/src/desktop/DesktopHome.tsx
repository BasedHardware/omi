import React, {useMemo, useState} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  desktopProjectionUnavailableCopy,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import {matchesSearchQuery} from '../searchText';
import type {ReadsPhase} from '../app/useDesktopReads';
import {FocusPressable} from '../ui/Pressable';
import {ReadStatus} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';
import {MaterialIcon} from '../ui/MaterialIcon';

import {GlanceCard} from './DesktopGlance';
import {EXPLORE_CHECKLIST, type ExploreCheck} from './exploreChecklist';
import {EmptyCopy, ReadRow, SectionTitle, TaskRow} from './DesktopRows';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';
import {OmiButton} from '../design/primitives';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

type Props = {
  draft: string;
  onRefresh: () => void;
  exploreDone?: Set<ExploreCheck> | null;
  onExploreGuide?: (check: ExploreCheck) => void;
  onOpenTasks?: () => void;
  onOpenConversations?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
};

/**
 * Inline read notice at the top of the list column: a quiet spinner while the
 * day is read, and a notice with Try Again when some history failed to load.
 * A read that failed outright is the page's own error state instead.
 */
export function DesktopReadBanner({
  onRefresh,
  readsPhase,
}: {
  onRefresh: () => void;
  readsPhase: ReadsPhase;
}) {
  const notice = useOmiStyles(createNoticeStyles);
  const theme = useOmiTheme();
  if (readsPhase === 'initial-loading' || readsPhase === 'refreshing') {
    return (
      <View accessibilityLabel="Reading your day" style={notice.row}>
        <ActivityIndicator color={theme.color.inkSecondary} size="small" />
        <Text style={notice.text}>Reading your day…</Text>
      </View>
    );
  }
  if (
    readsPhase === 'unavailable' ||
    readsPhase === 'saved-but-refresh-failed'
  ) {
    return (
      <View
        accessibilityLabel="History notice"
        style={[notice.row, notice.card]}>
        <MaterialIcon
          name="info"
          size={theme.size.iconSmall}
          color={theme.color.inkSecondary}
        />
        <Text style={notice.text}>Some of your history isn't loaded yet.</Text>
        <OmiButton compact label="Try Again" onPress={onRefresh} />
      </View>
    );
  }
  return null;
}

const createNoticeStyles = (t: OmiTheme) => ({
  row: {
    alignItems: 'center' as const,
    alignSelf: 'center' as const,
    flexDirection: 'row' as const,
    gap: t.space.sm + 2,
    marginTop: t.space.sm,
    maxWidth: t.layout.listColumn,
    minHeight: t.size.control,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.xs + 2,
    width: '100%' as const,
  },
  card: {
    backgroundColor: t.color.fill,
    borderRadius: t.radius.row,
  },
  text: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
  },
});

export function DesktopHome({
  draft,
  onRefresh,
  exploreDone = null,
  onExploreGuide,
  onOpenTasks,
  onOpenConversations,
  outcomes,
  reads,
  readsPhase,
}: Props) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const [wide, setWide] = useState(false);
  const query = draft.trim();
  const currents = useMemo(() => {
    return reads.filter(item => {
      if (item.kind === 'task') {
        return false;
      }
      return matchesSearchQuery(item.searchableText, query);
    });
  }, [query, reads]);
  const tasksOutcome = outcomes?.tasks ?? null;
  const visibleTasks = (
    tasksOutcome?.status === 'success' ? tasksOutcome.value.items : []
  ).filter(item => matchesSearchQuery(item.searchableText, query));
  // Only a successful empty read may claim emptiness. An unsettled read says
  // so plainly; a failed read surfaces its error — except a projection the
  // dev backend legitimately cannot serve yet, which reads as plain empty so
  // the card never shows a plumbing sentence.
  const isProjectionStub = (error: string) =>
    error === desktopProjectionUnavailableCopy;
  const tasksEmptyCopy =
    tasksOutcome === null
      ? 'Loading…'
      : tasksOutcome.status === 'error'
      ? isProjectionStub(tasksOutcome.error)
        ? 'No tasks yet'
        : tasksOutcome.error
      : query !== ''
      ? 'No tasks match this search.'
      : 'No tasks yet';
  const conversationsOutcome = outcomes?.conversations ?? null;
  const memoriesOutcome = outcomes?.memories ?? null;
  const currentsError = [conversationsOutcome, memoriesOutcome].find(
    outcome => outcome?.status === 'error',
  );
  const currentsEmptyCopy =
    conversationsOutcome === null || memoriesOutcome === null
      ? 'Loading…'
      : currentsError?.status === 'error'
      ? isProjectionStub(currentsError.error)
        ? 'Nothing captured yet'
        : currentsError.error
      : query !== ''
      ? 'Nothing captured matches this search.'
      : 'Nothing captured yet.';
  return (
    <View style={styles.home}>
      <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      <View style={styles.scroll}>
        <ScrollView
          scrollEventThrottle={16}
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          <GlanceCard outcomes={outcomes} />
          {exploreDone !== null &&
          exploreDone.size < EXPLORE_CHECKLIST.length ? (
            <View accessibilityLabel="Home explore" style={styles.section}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Getting started</SectionTitle>
              </View>
              {EXPLORE_CHECKLIST.map(item => {
                const done = exploreDone.has(item.id);
                return (
                  <FocusPressable
                    key={item.id}
                    accessibilityRole="button"
                    accessibilityLabel={`Guide: ${item.label}`}
                    onPress={() => onExploreGuide?.(item.id)}
                    style={({pressed}) => [
                      styles.exploreRow,
                      pressed && styles.pressed,
                    ]}>
                    <View
                      style={[
                        styles.exploreTick,
                        done && styles.exploreTickDone,
                      ]}>
                      {done ? (
                        <MaterialIcon
                          name="check"
                          size={13}
                          color={token.color.inkMuted}
                        />
                      ) : null}
                    </View>
                    <Text
                      style={[
                        styles.exploreLabel,
                        done && styles.exploreLabelDone,
                      ]}>
                      {item.label}
                    </Text>
                  </FocusPressable>
                );
              })}
            </View>
          ) : null}
          <View
            onLayout={event => setWide(event.nativeEvent.layout.width >= 760)}
            style={[styles.columns, wide && styles.columnsWide]}>
            <View
              accessibilityLabel="Home tasks"
              style={[styles.section, wide && styles.column]}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Tasks</SectionTitle>
                {visibleTasks.length > 0 &&
                tasksOutcome?.status === 'success' &&
                readsPhase !== 'initial-loading' &&
                readsPhase !== 'refreshing' ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel={
                      query ? 'Open tasks' : 'Show more tasks'
                    }
                    onPress={onOpenTasks}>
                    <Text style={styles.bannerAction}>
                      {query ? 'Open tasks' : 'Show more'}
                    </Text>
                  </FocusPressable>
                ) : null}
              </View>
              {visibleTasks.length > 0 ? (
                visibleTasks.slice(0, 3).map(item => (
                  <ShippingListInsert itemKey={item.id} key={item.id}>
                    <TaskRow item={item} />
                  </ShippingListInsert>
                ))
              ) : (
                <EmptyCopy>{tasksEmptyCopy}</EmptyCopy>
              )}
              {tasksOutcome?.status === 'success' &&
              !tasksOutcome.value.page.hasMore ? (
                <ReadStatus label="Tasks" mac page={tasksOutcome.value.page} />
              ) : null}
            </View>
            <View
              accessibilityLabel="Home currents"
              style={[styles.section, wide && styles.column]}>
              <View style={styles.sectionHeader}>
                <SectionTitle>Conversations & memories</SectionTitle>
                {currents.length > 0 &&
                conversationsOutcome?.status === 'success' &&
                !currentsError &&
                readsPhase !== 'initial-loading' &&
                readsPhase !== 'refreshing' ? (
                  <FocusPressable
                    accessibilityRole="button"
                    accessibilityLabel={
                      query ? 'Open conversations' : 'Show more conversations'
                    }
                    onPress={onOpenConversations}>
                    <Text style={styles.bannerAction}>
                      {query ? 'Open conversations' : 'Show more'}
                    </Text>
                  </FocusPressable>
                ) : null}
              </View>
              {currents.length > 0 ? (
                currents.slice(0, 3).map(item => (
                  <ShippingListInsert
                    itemKey={`${item.kind}-${item.id}`}
                    key={`${item.kind}-${item.id}`}>
                    <ReadRow item={item} />
                  </ShippingListInsert>
                ))
              ) : (
                <EmptyCopy>{currentsEmptyCopy}</EmptyCopy>
              )}
              {conversationsOutcome?.status === 'success' &&
              !conversationsOutcome.value.page.hasMore ? (
                <ReadStatus
                  label="Conversations"
                  mac
                  page={conversationsOutcome.value.page}
                />
              ) : null}
              {memoriesOutcome?.status === 'success' &&
              !memoriesOutcome.value.page.hasMore ? (
                <ReadStatus
                  label="Memories"
                  mac
                  page={memoriesOutcome.value.page}
                />
              ) : null}
            </View>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    scroll: {flex: 1},
    home: {flex: 1, gap: 12},
    columns: {gap: 32, marginBottom: 16},
    columnsWide: {flexDirection: 'row'},
    column: {flex: 1, minWidth: 0},
    exploreRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      paddingVertical: 7,
      paddingRight: 8,
    },
    exploreTick: {
      width: 22,
      height: 22,
      borderRadius: 11,
      borderWidth: 1,
      borderColor: token.color.lineStrong,
      alignItems: 'center',
      justifyContent: 'center',
    },
    exploreTickDone: {
      backgroundColor: token.color.glassSelected,
      borderColor: token.color.line,
    },
    exploreLabel: {
      fontSize: 13,
      color: token.color.ink,
    },
    exploreLabelDone: {color: token.color.inkMuted},
    sectionHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
    },
    banner: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexDirection: 'row',
      gap: 12,
      minHeight: 32,
      width: '100%',
      paddingHorizontal: 24,
      paddingVertical: 6,
    },
    bannerText: {
      color: token.color.inkMuted,
      flex: 1,
      flexShrink: 1,
      fontFamily: token.font,
      fontSize: token.type.meta,
      minWidth: 0,
    },
    bannerAction: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.meta,
      fontWeight: '600',
    },
    pressed: {opacity: 0.78},
    list: {flex: 1},
    // Quiet sections: a label over rows, no filled or bordered slab.
    section: {
      gap: 8,
      paddingVertical: 8,
    },
    listContent: {
      paddingTop: 8,
      paddingBottom: 32,
      paddingHorizontal: 24,
      maxWidth: 1040,
      width: '100%',
      alignSelf: 'center',
      gap: 24,
    },
  });
