import React, {useMemo} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type {ChatMessage} from '../chatClient';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {FocusPressable} from '../ui/Pressable';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {ReadStatus} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';
import {EmptyCopy, ReadRow, SectionTitle, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

type Props = {
  chatBusy: boolean;
  draft: string;
  hasOlderChat: boolean;
  loadingOlderChat: boolean;
  messages: ChatMessage[];
  onLoadOlderChat: () => void;
  onRefresh: () => void;
  onOpenRewind?: () => void;
  onOpenChat?: () => void;
  onOpenTasks?: () => void;
  onOpenConversations?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
};

export function DesktopReadBanner({
  onRefresh,
  readsPhase,
}: {
  onRefresh: () => void;
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
  return null;
}

export function DesktopHome({
  chatBusy,
  draft,
  hasOlderChat,
  messages,
  onRefresh,
  onOpenRewind,
  onOpenChat,
  onOpenTasks,
  onOpenConversations,
  outcomes,
  reads,
  readsPhase,
}: Props) {
  const fade = useScrollFade();
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
  const currentsEmptyCopy =
    conversationsOutcome === null || memoriesOutcome === null
      ? 'Conversations and memories will show here when your day is loaded.'
      : currentsError?.status === 'error'
      ? currentsError.error
      : query !== ''
      ? 'Nothing captured matches this search.'
      : 'Nothing captured yet.';
  return (
    <View style={styles.home}>
      <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      {messages.length > 0 || chatBusy || hasOlderChat ? (
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Continue chat"
          onPress={onOpenChat}
          style={styles.banner}>
          <Text style={styles.bannerAction}>
            {chatBusy ? 'Omi is replying…' : 'Continue chat'}
          </Text>
        </FocusPressable>
      ) : null}
      <ScrollFade visible={fade.visible} style={styles.scroll}>
        <ScrollView
          onLayout={fade.onLayout}
          onScroll={fade.onScroll}
          onContentSizeChange={fade.onContentSizeChange}
          scrollEventThrottle={16}
          contentContainerStyle={styles.listContent}
          style={styles.list}>
          <View
            accessibilityLabel="Home tasks"
            style={[styles.section, styles.sectionSpaced]}>
            <View style={styles.sectionHeader}>
              <SectionTitle>Tasks</SectionTitle>
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
            style={[styles.section, styles.sectionSpaced]}>
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
          <View accessibilityLabel="Home rewind" style={styles.section}>
            <SectionTitle>Screen history</SectionTitle>
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Open Recall"
              onPress={onOpenRewind}>
              <Text style={styles.bannerAction}>Open Recall</Text>
            </FocusPressable>
          </View>
        </ScrollView>
      </ScrollFade>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: {flex: 1},
  home: {flex: 1, gap: 12},
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
  sectionSpaced: {marginBottom: 14},
  section: {
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    gap: 8,
    padding: 16,
  },
  listContent: {paddingBottom: 32},
});
