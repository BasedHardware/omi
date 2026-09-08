import React, {useEffect, useMemo, useRef} from 'react';
import {
  ActivityIndicator,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {
  chatClockLabel,
  chatMessageDisplayText,
  chatSenderCopy,
  desktopBackendUnavailableCopy,
  desktopReadsCanRetry,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {FocusPressable} from '../ui/Pressable';
import {
  ReadStatus,
  coverageStatusCopy,
  emptyLibraryCopy,
} from '../ui/ReadStatus';
import {ShippingListInsert} from './ShippingStage';
import {EmptyCopy, ReadRow, SectionTitle, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

type Props = {
  chatBusy: boolean;
  conversationNotice?: string | null;
  draft: string;
  hasOlderChat: boolean;
  loadingOlderChat: boolean;
  memoryNotice?: string | null;
  memoriesLoadingMore?: boolean;
  onLoadMoreMemories?: () => void;
  messages: ChatMessage[];
  onLoadOlderChat: () => void;
  onRefresh: () => void;
  onOpenRewind?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  taskNotice?: string | null;
};

export function DesktopReadBanner({
  canRetry = true,
  onRefresh,
  readsPhase,
}: {
  canRetry?: boolean;
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
    if (!canRetry) {
      return (
        <View style={styles.banner}>
          <Text style={styles.bannerText}>{desktopBackendUnavailableCopy}</Text>
        </View>
      );
    }
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

function AskExchange({
  chatBusy,
  hasOlderChat,
  loadingOlderChat,
  messages,
  onLoadOlderChat,
}: {
  chatBusy: boolean;
  hasOlderChat: boolean;
  loadingOlderChat: boolean;
  messages: ChatMessage[];
  onLoadOlderChat: () => void;
}) {
  return (
    <View accessibilityLabel="Ask exchange" style={styles.exchange}>
      {hasOlderChat ? (
        <FocusPressable
          accessibilityLabel="Load earlier messages"
          accessibilityRole="button"
          disabled={loadingOlderChat}
          onPress={onLoadOlderChat}
          style={({pressed}) => [styles.older, pressed && styles.pressed]}>
          <Text style={styles.bannerAction}>
            {loadingOlderChat ? 'Loading earlier…' : 'Load earlier messages'}
          </Text>
        </FocusPressable>
      ) : null}
      {messages.map(item => (
        <View key={item.id} style={styles.exchangeRow}>
          <Text style={styles.rowMeta}>{chatSenderCopy(item.sender)}</Text>
          <Text
            accessibilityLabel={
              item.generationOutcome === 'failed'
                ? 'Failed response'
                : undefined
            }
            style={styles.rowTitle}>
            {chatMessageDisplayText(item, 'Response stopped.')}
          </Text>
          <Text style={styles.rowMeta}>
            {chatClockLabel(item.createdAt, Date.now()) || 'Time unavailable'}
          </Text>
        </View>
      ))}
      {chatBusy ? (
        <ActivityIndicator color={token.color.inkMuted} size="small" />
      ) : null}
    </View>
  );
}

export function DesktopHome({
  chatBusy,
  conversationNotice = null,
  draft,
  hasOlderChat,
  loadingOlderChat,
  memoryNotice = null,
  memoriesLoadingMore = false,
  messages,
  onLoadMoreMemories,
  onLoadOlderChat,
  onRefresh,
  onOpenRewind,
  outcomes,
  reads,
  readsPhase,
  taskNotice = null,
}: Props) {
  const chatScrollRef = useRef<ScrollView>(null);
  const shouldFollowChat = useRef(true);
  useEffect(() => {
    if (chatBusy) {
      shouldFollowChat.current = true;
    }
  }, [chatBusy]);
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
      : emptyLibraryCopy(
          'Tasks',
          tasksOutcome.value.page,
          query !== '',
          'No tasks match this search.',
          'No tasks yet',
          taskNotice === desktopBackendUnavailableCopy,
        );
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
      : coverageStatusCopy(
          conversationsOutcome.status === 'success'
            ? conversationsOutcome.value.page
            : null,
          memoriesOutcome.status === 'success'
            ? memoriesOutcome.value.page
            : null,
          null,
          query !== ''
            ? {
                conversations:
                  conversationNotice === desktopBackendUnavailableCopy,
                memories: memoryNotice === desktopBackendUnavailableCopy,
              }
            : {},
        ) ??
        (query !== ''
          ? 'Nothing captured matches this search.'
          : 'Nothing captured yet.');
  return (
    <View style={styles.home}>
      <DesktopReadBanner
        canRetry={desktopReadsCanRetry(outcomes)}
        onRefresh={onRefresh}
        readsPhase={readsPhase}
      />
      {messages.length > 0 || chatBusy || hasOlderChat ? (
        <ScrollView
          contentContainerStyle={styles.chatContent}
          onContentSizeChange={() => {
            if (shouldFollowChat.current) {
              chatScrollRef.current?.scrollToEnd({animated: true});
            }
          }}
          onScroll={(event: NativeSyntheticEvent<NativeScrollEvent>) => {
            const {contentOffset, contentSize, layoutMeasurement} =
              event.nativeEvent;
            shouldFollowChat.current =
              contentOffset.y + layoutMeasurement.height >=
              contentSize.height - 48;
          }}
          ref={chatScrollRef}
          scrollEventThrottle={16}
          style={styles.chatList}>
          <AskExchange
            chatBusy={chatBusy}
            hasOlderChat={hasOlderChat}
            loadingOlderChat={loadingOlderChat}
            messages={messages}
            onLoadOlderChat={() => {
              shouldFollowChat.current = false;
              onLoadOlderChat();
            }}
          />
        </ScrollView>
      ) : null}
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        <View
          accessibilityLabel="Home tasks"
          style={[styles.section, styles.sectionSpaced]}>
          <SectionTitle>Tasks</SectionTitle>
          {visibleTasks.length > 0 ? (
            visibleTasks.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <TaskRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>{tasksEmptyCopy}</EmptyCopy>
          )}
          {tasksOutcome?.status === 'success' && visibleTasks.length > 0 ? (
            <ReadStatus
              continueUnavailable={taskNotice === desktopBackendUnavailableCopy}
              label="Tasks"
              mac
              page={tasksOutcome.value.page}
            />
          ) : null}
          {taskNotice === desktopBackendUnavailableCopy ? (
            <Text accessibilityRole="alert" style={styles.rowMeta}>
              {taskNotice}
            </Text>
          ) : null}
        </View>
        <View
          accessibilityLabel="Home currents"
          style={[styles.section, styles.sectionSpaced]}>
          <SectionTitle>Conversations & memories</SectionTitle>
          {currents.length > 0 ? (
            currents.map(item => (
              <ShippingListInsert
                itemKey={`${item.kind}-${item.id}`}
                key={`${item.kind}-${item.id}`}>
                <ReadRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>{currentsEmptyCopy}</EmptyCopy>
          )}
          {conversationsOutcome?.status === 'success' && currents.length > 0 ? (
            <ReadStatus
              continueUnavailable={
                conversationNotice === desktopBackendUnavailableCopy
              }
              label="Conversations"
              mac
              page={conversationsOutcome.value.page}
            />
          ) : null}
          {memoriesOutcome?.status === 'success' && currents.length > 0 ? (
            <ReadStatus
              continueUnavailable={
                memoryNotice === desktopBackendUnavailableCopy
              }
              label="Memories"
              mac
              page={memoriesOutcome.value.page}
            />
          ) : null}
          {conversationNotice === desktopBackendUnavailableCopy ? (
            <Text accessibilityRole="alert" style={styles.rowMeta}>
              {conversationNotice}
            </Text>
          ) : null}
          {memoryNotice !== null ? (
            <Text accessibilityRole="alert" style={styles.rowMeta}>
              {memoryNotice}
            </Text>
          ) : null}
          {memoriesOutcome?.status === 'success' &&
          memoriesOutcome.value.page.hasMore &&
          onLoadMoreMemories ? (
            <FocusPressable
              accessibilityLabel="Load more memories"
              accessibilityRole="button"
              disabled={memoriesLoadingMore}
              onPress={onLoadMoreMemories}
              style={styles.pageAction}>
              <Text style={styles.bannerAction}>
                {memoriesLoadingMore ? 'Loading…' : 'Load more memories'}
              </Text>
            </FocusPressable>
          ) : null}
        </View>
        <View accessibilityLabel="Home rewind" style={styles.section}>
          <SectionTitle>Screen history</SectionTitle>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Open Rewind"
            onPress={onOpenRewind}>
            <Text style={styles.bannerAction}>Browse screen history</Text>
          </FocusPressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  home: {flex: 1, gap: 12},
  chatList: {maxHeight: '42%'},
  chatContent: {paddingBottom: 4},
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
  older: {alignSelf: 'flex-start', minHeight: 28, paddingVertical: 4},
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
  exchange: {gap: 4, paddingBottom: 12},
  exchangeRow: {gap: 3, paddingVertical: 6},
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
  },
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
  },
  pageAction: {minHeight: 44, justifyContent: 'center'},
});
