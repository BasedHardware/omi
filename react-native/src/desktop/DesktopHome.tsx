import React, {useMemo} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Monitor from 'lucide-react-native/icons/monitor';
import type {ChatMessage} from '../chatClient';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {FocusPressable} from '../ui/Pressable';
import type {DesktopSession} from './desktopChrome';
import {ShippingListInsert} from './ShippingStage';
import {EmptyCopy, ReadRow, SectionTitle, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

type Props = {
  chatBusy: boolean;
  draft: string;
  messages: ChatMessage[];
  onRefresh: () => void;
  onSignIn: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
};

export function RewindPanel() {
  return (
    <View style={styles.centerState}>
      <Monitor color={token.color.inkMuted} size={28} />
      <Text style={styles.emptyTitle}>
        Screen history is ready when capture is on
      </Text>
      <Text style={styles.emptyCopy}>
        Captured frames stay navigable by time and application.
      </Text>
    </View>
  );
}

function SessionBanner({
  onRefresh,
  onSignIn,
  readsPhase,
  session,
  signingIn,
}: {
  onRefresh: () => void;
  onSignIn: () => void;
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
}) {
  if (session === 'probing') {
    return (
      <View accessibilityLabel="Session check" style={styles.banner}>
        <ActivityIndicator color={token.color.inkMuted} size="small" />
        <Text style={styles.bannerText}>Restoring your session…</Text>
      </View>
    );
  }
  if (session === 'signed-out') {
    return (
      <View style={styles.banner}>
        <Text style={styles.bannerText}>
          Sign in to load conversations and memories.
        </Text>
        <FocusPressable
          accessibilityLabel="Sign in"
          accessibilityRole="button"
          disabled={signingIn}
          onPress={onSignIn}
          style={({pressed}) => [
            styles.bannerActionHit,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.bannerAction}>
            {signingIn ? 'Signing in…' : 'Sign in'}
          </Text>
        </FocusPressable>
      </View>
    );
  }
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

function AskExchange({
  chatBusy,
  messages,
}: {
  chatBusy: boolean;
  messages: ChatMessage[];
}) {
  return (
    <View accessibilityLabel="Ask exchange" style={styles.exchange}>
      {messages.map(item => (
        <View key={item.id} style={styles.exchangeRow}>
          <Text style={styles.rowMeta}>
            {item.sender === 'human' ? 'You' : 'Omi'}
          </Text>
          <Text style={styles.rowTitle}>{item.text}</Text>
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
  draft,
  messages,
  onRefresh,
  onSignIn,
  outcomes,
  reads,
  readsPhase,
  session,
  signingIn,
}: Props) {
  const query = draft.trim();
  const normalized = query.toLocaleLowerCase();
  const conversations = useMemo(() => {
    return reads.filter(item => {
      if (item.kind !== 'conversation') {
        return false;
      }
      return (
        normalized === '' ||
        item.searchableText.toLocaleLowerCase().includes(normalized)
      );
    });
  }, [normalized, reads]);
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
  const visibleTasks = tasks.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  return (
    <View style={styles.home}>
      <SessionBanner
        onRefresh={onRefresh}
        onSignIn={onSignIn}
        readsPhase={readsPhase}
        session={session}
        signingIn={signingIn}
      />
      <ScrollView
        contentContainerStyle={styles.listContent}
        style={styles.list}>
        {messages.length > 0 || chatBusy ? (
          <AskExchange chatBusy={chatBusy} messages={messages} />
        ) : null}
        <View accessibilityLabel="Home tasks" style={styles.section}>
          <SectionTitle>Today</SectionTitle>
          {visibleTasks.length > 0 ? (
            visibleTasks.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <TaskRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>No tasks yet</EmptyCopy>
          )}
        </View>
        <View accessibilityLabel="Home currents" style={styles.section}>
          <SectionTitle>Conversations</SectionTitle>
          {conversations.length > 0 ? (
            conversations.map(item => (
              <ShippingListInsert
                itemKey={`${item.kind}-${item.id}`}
                key={`${item.kind}-${item.id}`}>
                <ReadRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <EmptyCopy>
              {readsPhase === 'ready'
                ? query !== ''
                  ? 'Nothing captured matches this search.'
                  : 'Conversations will show here when your day is loaded.'
                : 'Conversations will show here when your day is loaded.'}
            </EmptyCopy>
          )}
        </View>
        <View accessibilityLabel="Home rewind" style={styles.section}>
          <SectionTitle>Screen history</SectionTitle>
          <EmptyCopy>Screen history is ready when capture is on</EmptyCopy>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  home: {flex: 1, gap: 12},
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
  bannerActionHit: {
    flexShrink: 0,
    paddingHorizontal: 4,
    paddingVertical: 6,
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
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  listContent: {gap: 14, paddingBottom: 32},
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
  emptyTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    textAlign: 'center',
  },
  emptyCopy: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    lineHeight: 18,
    marginTop: 6,
    textAlign: 'center',
  },
  centerState: {
    alignItems: 'center',
    flex: 1,
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 40,
  },
});
