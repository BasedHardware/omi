import React, {useMemo, useState} from 'react';
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
import {ShippingPressable} from './ShippingPressable';
import {ShippingListInsert} from './ShippingStage';
import {EmptyCopy, ReadRow, SectionTitle, TaskRow} from './DesktopRows';
import {desktopTokens as token} from './tokens';

export const homeFilters = [
  'All',
  'Conversations',
  'Memories',
  'Tasks',
  'Rewind',
] as const;

export type HomeFilter = (typeof homeFilters)[number];

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

function FilterText({
  active,
  label,
  onPress,
}: {
  active: boolean;
  label: HomeFilter;
  onPress: () => void;
}) {
  return (
    <ShippingPressable
      accessibilityLabel={`Filter ${label}`}
      accessibilityRole="button"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={styles.filterItem}>
      <Text style={[styles.filterText, active && styles.filterTextActive]}>
        {label}
      </Text>
    </ShippingPressable>
  );
}

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
            styles.signInButton,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.signInText}>
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
  const [filter, setFilter] = useState<HomeFilter>('All');
  const query = draft.trim();
  const normalized = query.toLocaleLowerCase();
  const currents = useMemo(() => {
    return reads.filter(item => {
      if (item.kind === 'task') {
        return false;
      }
      const kindMatches =
        filter === 'All' ||
        (filter === 'Conversations' && item.kind === 'conversation') ||
        (filter === 'Memories' && item.kind === 'memory');
      return (
        kindMatches &&
        (normalized === '' ||
          item.searchableText.toLocaleLowerCase().includes(normalized))
      );
    });
  }, [filter, normalized, reads]);
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
  const visibleTasks = tasks.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  const showCurrents = filter !== 'Tasks' && filter !== 'Rewind';
  const showTasks = filter === 'All' || filter === 'Tasks';
  return (
    <View style={styles.home}>
      <View accessibilityRole="tablist" style={styles.filterRow}>
        {homeFilters.map(label => (
          <FilterText
            active={filter === label}
            key={label}
            label={label}
            onPress={() => setFilter(label)}
          />
        ))}
      </View>
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
        {filter === 'Rewind' ? (
          <RewindPanel />
        ) : (
          <>
            {showCurrents ? (
              <View accessibilityLabel="Home currents">
                <SectionTitle>Currents</SectionTitle>
                {currents.length > 0 ? (
                  currents.map(item => (
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
                        : 'Nothing current right now.'
                      : 'Currents will show here when your day is loaded.'}
                  </EmptyCopy>
                )}
              </View>
            ) : null}
            {showTasks ? (
              <View accessibilityLabel="Home tasks">
                <SectionTitle>Tasks</SectionTitle>
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
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  home: {flex: 1},
  filterRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    minHeight: 32,
  },
  filterItem: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
  },
  filterText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  filterTextActive: {color: token.color.ink},
  banner: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    minHeight: 28,
  },
  bannerText: {
    color: token.color.inkMuted,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.meta,
  },
  bannerAction: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.meta,
    fontWeight: '600',
  },
  signInButton: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.control,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  signInText: {
    color: token.color.white,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  pressed: {opacity: 0.78},
  list: {flex: 1},
  listContent: {paddingBottom: 24, paddingTop: 4},
  exchange: {gap: 4, paddingBottom: 8},
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
