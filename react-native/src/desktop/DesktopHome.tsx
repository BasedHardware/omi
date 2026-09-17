import React, {useMemo} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import type {PostSetupHomeCue} from '../app/usePostSetupHomeCue';
import type {TimelineRecall} from '../timeline/mixedTimeline';
import {TimelineSections, buildTimelineItems} from '../timeline/TimelineHome';
import {FocusPressable} from '../ui/Pressable';
import {ScrollFade} from './ScrollFade';
import {ReadStatus} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';

import {EmptyCopy, SectionTitle, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

type Props = {
  draft: string;
  onRefresh: () => void;
  onOpenRewind?: () => void;
  onOpenTasks?: () => void;
  onOpenConversations?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  postSetupHomeCue?: PostSetupHomeCue;
  recall?: readonly TimelineRecall[];
  recallStatus?: 'ready' | 'loading' | 'error' | 'unavailable';
  recallNotice?: string | null;
};

export function DesktopReadBanner({
  onRefresh,
  postSetupHomeCue = null,
  readsPhase,
}: {
  onRefresh: () => void;
  postSetupHomeCue?: PostSetupHomeCue;
  readsPhase: ReadsPhase;
}) {
  if (readsPhase === 'initial-loading' || readsPhase === 'refreshing') {
    return (
      <View accessibilityLabel="Reading your day" style={styles.banner}>
        <ActivityIndicator color={token.color.inkMuted} size="small" />
        <Text style={styles.bannerText}>Reading your day…</Text>
      </View>
    );
  }
  if (
    readsPhase === 'unavailable' ||
    readsPhase === 'saved-but-refresh-failed'
  ) {
    return (
      <FocusPressable
        accessibilityLabel="Try again"
        accessibilityRole="button"
        onPress={onRefresh}
        style={({pressed}) => [styles.banner, pressed && styles.pressed]}>
        <Text style={styles.bannerText}>
          Some of your history isn't loaded yet.
        </Text>
        <Text style={styles.bannerAction}>Try again</Text>
      </FocusPressable>
    );
  }
  // Post-setup prove-it: only after reads settled ready. Never invents Claude.
  if (postSetupHomeCue === 'proven' && readsPhase === 'ready') {
    return (
      <View accessibilityLabel="Home prove-it" style={styles.banner}>
        <Text style={styles.bannerText}>
          You're set. Home can read conversations, memories, and tasks from your
          account.
        </Text>
      </View>
    );
  }
  return null;
}

export function DesktopHome({
  draft,
  onRefresh,
  onOpenRewind,
  onOpenTasks,
  onOpenConversations,
  outcomes,
  postSetupHomeCue = null,
  reads,
  readsPhase,
  recall = [],
  recallStatus = 'ready',
  recallNotice = null,
}: Props) {
  const query = draft.trim();
  const normalized = query.toLocaleLowerCase();
  const currents = useMemo(() => {
    return reads.filter(item => {
      if (item.kind === 'task') {
        return false;
      }
      return (
        normalized === '' ||
        item.searchableText.toLocaleLowerCase().includes(normalized)
      );
    });
  }, [normalized, reads]);
  const tasksOutcome = outcomes?.tasks ?? null;
  const visibleTasks = (
    tasksOutcome?.status === 'success' ? tasksOutcome.value.items : []
  ).filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  // Only a successful empty read may claim emptiness. An unsettled or failed
  // read stays truthful instead of inventing "no tasks yet".
  const tasksEmptyCopy =
    tasksOutcome === null
      ? 'Tasks load with your day.'
      : tasksOutcome.status === 'error'
      ? tasksOutcome.error
      : query !== ''
      ? 'No tasks match this search.'
      : 'No tasks yet';
  const conversationsOutcome = outcomes?.conversations ?? null;
  const memoriesOutcome = outcomes?.memories ?? null;
  const currentsError = [conversationsOutcome, memoriesOutcome].find(
    outcome => outcome?.status === 'error',
  );
  return (
    <View style={styles.home}>
      <DesktopReadBanner
        onRefresh={onRefresh}
        postSetupHomeCue={postSetupHomeCue}
        readsPhase={readsPhase}
      />
      <ScrollFade visible style={styles.scroll}>
        <ScrollView
          scrollEventThrottle={16}
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          <View accessibilityLabel="Home tasks" style={styles.section}>
            <View style={styles.sectionHeader}>
              <SectionTitle>Action items</SectionTitle>
              {visibleTasks.length > 0 &&
              tasksOutcome?.status === 'success' &&
              readsPhase !== 'initial-loading' &&
              readsPhase !== 'refreshing' ? (
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel={query ? 'Open tasks' : 'Show more tasks'}
                  onPress={onOpenTasks}>
                  <Text style={styles.bannerAction}>
                    {query ? 'Open tasks' : 'Show more'}
                  </Text>
                </FocusPressable>
              ) : null}
            </View>
            {visibleTasks.length > 0 ? (
              visibleTasks.slice(0, 5).map(item => (
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
          {recallNotice ? (
            <Text accessibilityRole="alert" style={styles.recallCopy}>
              {recallNotice}
            </Text>
          ) : null}
          <View accessibilityLabel="Home timeline" style={styles.section}>
            <TimelineSections
              items={buildTimelineItems({
                conversations: currents
                  .filter(
                    (item): item is Extract<typeof item, {kind: 'conversation'}> =>
                      item.kind === 'conversation',
                  )
                  .map(item => ({
                    kind: 'conversation' as const,
                    id: item.id,
                    title: item.title,
                    summary: item.summary,
                    searchableText: item.searchableText,
                    atMs: Number.isFinite(
                      Date.parse(item.startedAt ?? item.createdAt),
                    )
                      ? Date.parse(item.startedAt ?? item.createdAt)
                      : null,
                  })),
                recall,
                query,
              })}
              nowEpochMilliseconds={Date.now()}
              status={
                recallStatus === 'error' && currentsError
                  ? 'error'
                  : readsPhase === 'initial-loading' ||
                    readsPhase === 'refreshing' ||
                    recallStatus === 'loading'
                  ? 'loading'
                  : 'ready'
              }
              onOpenItem={item => {
                if (item.kind === 'conversation') {
                  onOpenConversations?.();
                } else {
                  onOpenRewind?.();
                }
              }}
            />
          </View>
        </ScrollView>
      </ScrollFade>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: {flex: 1},
  home: {flex: 1, gap: 12},
  columns: {gap: 16, marginBottom: 16},
  columnsWide: {flexDirection: 'row'},
  column: {flex: 1, minWidth: 0},
  recallRow: {flexDirection: 'row', alignItems: 'center', gap: 14},
  recallIcon: {
    width: 42,
    height: 42,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: token.color.glassQuiet,
  },
  recallCopy: {
    fontSize: 12,
    lineHeight: 19,
    marginTop: 5,
    color: token.color.inkMuted,
  },
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
  section: {
    backgroundColor: token.color.glassStrong,
    borderWidth: 1,
    borderColor: token.color.line,
    borderRadius: 18,
    gap: 12,
    padding: 24,
  },
  listContent: {
    paddingTop: 8,
    paddingBottom: 32,
    paddingHorizontal: 24,
    maxWidth: 1040,
    width: '100%',
    alignSelf: 'center',
  },
});
