import React, {memo, useCallback, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import CalendarDays from 'lucide-react-native/icons/calendar-days';
import CheckCircle2 from 'lucide-react-native/icons/circle-check';
import Clock from 'lucide-react-native/icons/clock';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Grid2X2 from 'lucide-react-native/icons/grid-2x2';
import House from 'lucide-react-native/icons/house';
import Library from 'lucide-react-native/icons/library';
import ListFilter from 'lucide-react-native/icons/list-filter';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Monitor from 'lucide-react-native/icons/monitor';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Settings from 'lucide-react-native/icons/settings';
import Sparkles from 'lucide-react-native/icons/sparkles';
import type {ChatMessage} from '../chatClient';
import type {
  ConversationProjection,
  DesktopReadOutcomes,
  DesktopReadProjection,
  MemoryProjection,
  TaskProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {FocusPressable} from '../ui/Pressable';
import {
  desktopNavBarHeight,
  desktopNavItems,
  desktopNavTopInset,
  desktopSearchPlaceholder,
  desktopTrafficLightButton,
  desktopTrafficLightLeading,
  desktopTrafficLightRowWidth,
  desktopWindowInset,
  visibleChatError,
  type DesktopNavItem,
  type DesktopSession,
} from './desktopChrome';

export type {DesktopSession};
import {DesktopSettings} from './DesktopSettings';
import {ShippingPressable} from './ShippingPressable';
import {ShippingListInsert, ShippingStage} from './ShippingStage';
import {desktopTokens as token} from './tokens';

type DesktopRoute = DesktopNavItem | 'Settings';
type MemoryHub =
  | 'Activity'
  | 'Conversations'
  | 'Memories'
  | 'Rewind'
  | 'Brain Map';

type Props = {
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
  draft: string;
  messages: ChatMessage[];
  chatBusy: boolean;
  chatError: string | null;
  onRefresh: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onDraftChange: (value: string) => void;
  onSend: () => void;
};

const navIcons: Record<DesktopNavItem, typeof Search> = {
  Home: House,
  Library: Library,
  Tasks: ListFilter,
  Rewind: Clock,
  Apps: Puzzle,
};

function FilterText({
  active = false,
  label,
  onPress,
}: {
  active?: boolean;
  label: string;
  onPress?: () => void;
}) {
  return (
    <ShippingPressable
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

function ResultRow({item}: {item: DesktopReadProjection}) {
  const timestamp =
    item.kind === 'conversation'
      ? Date.parse(item.startedAt ?? item.createdAt)
      : item.kind === 'memory'
      ? (item.timestamp ?? 0) * 1000
      : item.createdAt * 1000;
  const time =
    timestamp > 0
      ? new Date(timestamp).toLocaleTimeString(undefined, {
          hour: 'numeric',
          minute: '2-digit',
        })
      : '';
  const Icon =
    item.kind === 'conversation'
      ? MessageCircle
      : item.kind === 'memory'
      ? Sparkles
      : CheckCircle2;
  return (
    <View style={styles.resultRow}>
      <View style={styles.glyph}>
        <Icon color={token.color.ink} size={16} />
      </View>
      <View style={styles.resultCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {item.title}
        </Text>
        <Text numberOfLines={1} style={styles.rowMeta}>
          {[time, item.kind === 'conversation' ? item.summary : item.kind]
            .filter(value => value !== '')
            .join(' · ')}
        </Text>
      </View>
    </View>
  );
}

const ConversationRow = memo(function ConversationRow({
  item,
}: {
  item: ConversationProjection;
}) {
  const time = new Date(item.startedAt ?? item.createdAt).toLocaleTimeString(
    undefined,
    {hour: 'numeric', minute: '2-digit'},
  );
  return (
    <View style={styles.resultRow}>
      <View style={styles.glyph}>
        <MessageCircle color={token.color.ink} size={16} />
      </View>
      <View style={styles.resultCopy}>
        <Text style={styles.rowTitle}>{item.title}</Text>
        <Text style={styles.rowMeta}>
          {time} · {item.summary}
        </Text>
      </View>
    </View>
  );
});

const MemoryRow = memo(function MemoryRow({item}: {item: MemoryProjection}) {
  return (
    <View style={styles.memoryCard}>
      <Text numberOfLines={3} style={styles.memoryText}>
        {item.summary}
      </Text>
      <Text style={styles.rowMeta}>
        {item.timestamp === null
          ? 'Date unavailable'
          : new Date(item.timestamp * 1000).toLocaleDateString()}
      </Text>
    </View>
  );
});

const TaskRow = memo(function TaskRow({item}: {item: TaskProjection}) {
  return (
    <View style={styles.taskRow}>
      <View
        style={[styles.taskCircle, item.completed && styles.taskCircleDone]}
      />
      <Text style={[styles.taskText, item.completed && styles.taskTextDone]}>
        {item.title}
      </Text>
    </View>
  );
});

function SessionBanner({
  session,
  readsPhase,
  signingIn,
  onRefresh,
  onSignIn,
}: {
  session: DesktopSession;
  readsPhase: ReadsPhase;
  signingIn: boolean;
  onRefresh: () => void;
  onSignIn: () => void;
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

function HomeStage({
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
  const [filter, setFilter] = useState<
    'All' | 'Conversations' | 'Memories' | 'Tasks' | 'Rewind'
  >('All');
  const query = draft.trim();
  const normalized = query.toLocaleLowerCase();
  const currentItems = useMemo(() => {
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
  const showCurrents = filter !== 'Tasks';
  const showTasks = filter === 'All' || filter === 'Tasks';
  return (
    <View style={styles.page}>
      <View style={styles.filterRow}>
        {(['All', 'Conversations', 'Memories', 'Tasks', 'Rewind'] as const).map(
          label => (
            <FilterText
              active={filter === label}
              key={label}
              label={label}
              onPress={() => setFilter(label)}
            />
          ),
        )}
      </View>
      <SessionBanner
        onRefresh={onRefresh}
        onSignIn={onSignIn}
        readsPhase={readsPhase}
        session={session}
        signingIn={signingIn}
      />
      <ScrollView
        contentContainerStyle={styles.list}
        style={styles.stageScroll}>
        {messages.length > 0 || chatBusy ? (
          <View style={styles.conversation}>
            {messages.map(item => (
              <View key={item.id} style={styles.chatRow}>
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
        ) : null}
        {showCurrents ? (
          <View accessibilityLabel="Home currents">
            <Text style={styles.sectionTitle}>Currents</Text>
            {currentItems.length > 0 ? (
              currentItems.map(item => (
                <ShippingListInsert
                  itemKey={`${item.kind}-${item.id}`}
                  key={`${item.kind}-${item.id}`}>
                  <ResultRow item={item} />
                </ShippingListInsert>
              ))
            ) : (
              <Text style={styles.emptyCopy}>
                {readsPhase === 'ready'
                  ? query !== ''
                    ? 'Nothing captured matches this search.'
                    : 'Nothing current right now.'
                  : 'Currents will show here when your day is loaded.'}
              </Text>
            )}
          </View>
        ) : null}
        {showTasks ? (
          <View accessibilityLabel="Home tasks">
            <Text style={styles.sectionTitle}>Tasks</Text>
            {visibleTasks.length > 0 ? (
              visibleTasks.map(item => (
                <ShippingListInsert itemKey={item.id} key={item.id}>
                  <TaskRow item={item} />
                </ShippingListInsert>
              ))
            ) : (
              <Text style={styles.emptyCopy}>No tasks yet</Text>
            )}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

function LibraryPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const [hub, setHub] = useState<MemoryHub>('Activity');
  const conversations =
    outcomes?.conversations.status === 'success'
      ? outcomes.conversations.value.items
      : [];
  const memories =
    outcomes?.memories.status === 'success'
      ? outcomes.memories.value.items
      : [];
  return (
    <View style={styles.singlePanel}>
      <View style={styles.filterRow}>
        {(
          [
            'Activity',
            'Conversations',
            'Memories',
            'Rewind',
            'Brain Map',
          ] as const
        ).map(label => (
          <FilterText
            active={hub === label}
            key={label}
            label={label}
            onPress={() => setHub(label)}
          />
        ))}
      </View>
      {hub === 'Conversations' ? (
        <ScrollView contentContainerStyle={styles.list}>
          {conversations.length > 0 ? (
            conversations.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <ConversationRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          )}
        </ScrollView>
      ) : hub === 'Memories' ? (
        <ScrollView contentContainerStyle={styles.list}>
          {memories.length > 0 ? (
            memories.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <MemoryRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          )}
        </ScrollView>
      ) : hub === 'Rewind' ? (
        <RewindState />
      ) : hub === 'Brain Map' ? (
        <View style={styles.centerState}>
          <Grid2X2 color={token.color.inkMuted} size={28} />
          <Text style={styles.emptyTitle}>No connections to show yet.</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          <Text style={styles.sectionTitle}>Activity</Text>
          {conversations.length > 0 ? (
            conversations.map(item => (
              <ShippingListInsert itemKey={item.id} key={item.id}>
                <ConversationRow item={item} />
              </ShippingListInsert>
            ))
          ) : (
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          )}
        </ScrollView>
      )}
    </View>
  );
}

function RewindState() {
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

function TasksPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const [query, setQuery] = useState('');
  const tasks =
    outcomes?.tasks.status === 'success' ? outcomes.tasks.value.items : [];
  const normalized = query.trim().toLocaleLowerCase();
  const visible = tasks.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  return (
    <View style={styles.singlePanel}>
      <View style={styles.tasksHeader}>
        <Text style={styles.pageTitle}>Tasks</Text>
        <View style={styles.searchControl}>
          <Search color={token.color.inkMuted} size={15} />
          <TextInput
            onChangeText={setQuery}
            placeholder="Search tasks…"
            placeholderTextColor={token.color.inkFaint}
            style={styles.searchInput}
            value={query}
          />
        </View>
      </View>
      <Text style={styles.sectionTitle}>Today</Text>
      <ScrollView
        contentContainerStyle={styles.list}
        style={styles.stageScroll}>
        {visible.length > 0 ? (
          visible.map(item => (
            <ShippingListInsert itemKey={item.id} key={item.id}>
              <TaskRow item={item} />
            </ShippingListInsert>
          ))
        ) : (
          <Text style={styles.emptyCopy}>No tasks yet</Text>
        )}
      </ScrollView>
    </View>
  );
}

const imports = [
  ['Calendar', 'Google Calendar', CalendarDays],
  ['Email', 'Gmail', Archive],
  ['Local files', 'This Mac', Folder],
  ['Apple Notes', 'Private notes', FileText],
  ['X (Twitter)', 'Your posts and bookmarks', Sparkles],
  ['ChatGPT', 'Memory import', Puzzle],
] as const;

function AppsPage() {
  return (
    <View style={styles.singlePanel}>
      <Text style={styles.pageTitle}>Imports</Text>
      <ScrollView contentContainerStyle={styles.appGrid}>
        {imports.map(([name, source, Icon]) => (
          <View key={name} style={styles.appCard}>
            <View style={styles.appCardHeader}>
              <View style={styles.appIcon}>
                <Icon color={token.color.ink} size={18} />
              </View>
              <View>
                <Text style={styles.rowTitle}>{name}</Text>
                <Text style={styles.rowMeta}>{source}</Text>
              </View>
            </View>
            <Text style={styles.rowMeta}>Not connected</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

export function DesktopApp({
  outcomes,
  reads,
  readsPhase,
  session,
  signingIn,
  draft,
  messages,
  chatBusy,
  chatError,
  onRefresh,
  onSignIn,
  onSignOut,
  onDraftChange,
  onSend,
}: Props) {
  const [route, setRoute] = useState<DesktopRoute>('Home');
  const navigate = useCallback((next: DesktopRoute) => setRoute(next), []);
  const error = visibleChatError(session, chatError);
  return (
    <View accessibilityLabel="Omi desktop" style={styles.root}>
      <View style={styles.navbar}>
        <View
          accessibilityLabel="Window controls"
          style={styles.trafficLights}
        />
        <View style={styles.navItems}>
          {desktopNavItems.map(label => {
            const Icon = navIcons[label];
            return (
              <ShippingPressable
                accessibilityRole="button"
                accessibilityState={{selected: route === label}}
                active={route === label}
                key={label}
                onPress={() => navigate(label)}
                style={styles.navItem}>
                <Icon color={token.color.ink} size={14} />
                <Text
                  style={[
                    styles.navText,
                    route === label && styles.navTextActive,
                  ]}>
                  {label}
                </Text>
              </ShippingPressable>
            );
          })}
        </View>
        <View style={styles.omnibar}>
          <Search color={token.color.inkMuted} size={15} />
          <TextInput
            accessibilityLabel="Search what you have seen and heard"
            onChangeText={onDraftChange}
            onSubmitEditing={onSend}
            placeholder={desktopSearchPlaceholder}
            placeholderTextColor={token.color.inkMuted}
            style={styles.omnibarInput}
            value={draft}
          />
          <FocusPressable
            accessibilityLabel="Send"
            accessibilityRole="button"
            onPress={onSend}
            style={({pressed}) => [
              styles.sendButton,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.sendText}>Ask</Text>
          </FocusPressable>
        </View>
        <ShippingPressable
          accessibilityLabel="Settings"
          active={route === 'Settings'}
          onPress={() => navigate('Settings')}
          style={styles.utilityButton}>
          <Settings color={token.color.ink} size={14} />
        </ShippingPressable>
      </View>
      {error !== null ? <Text style={styles.omnibarError}>{error}</Text> : null}
      <ShippingStage stageKey={route} variant="page">
        {route === 'Home' ? (
          <HomeStage
            chatBusy={chatBusy}
            chatError={chatError}
            draft={draft}
            messages={messages}
            onDraftChange={onDraftChange}
            onRefresh={onRefresh}
            onSend={onSend}
            onSignIn={onSignIn}
            onSignOut={onSignOut}
            outcomes={outcomes}
            reads={reads}
            readsPhase={readsPhase}
            session={session}
            signingIn={signingIn}
          />
        ) : route === 'Library' ? (
          <LibraryPage outcomes={outcomes} />
        ) : route === 'Tasks' ? (
          <TasksPage outcomes={outcomes} />
        ) : route === 'Rewind' ? (
          <View style={styles.singlePanel}>
            <RewindState />
          </View>
        ) : route === 'Apps' ? (
          <AppsPage />
        ) : (
          <View style={styles.singlePanel}>
            <DesktopSettings
              onSignIn={onSignIn}
              onSignOut={onSignOut}
              session={session}
              signingIn={signingIn}
            />
          </View>
        )}
      </ShippingStage>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'transparent',
    flex: 1,
    gap: desktopWindowInset,
    paddingBottom: desktopWindowInset,
    paddingHorizontal: desktopWindowInset,
    paddingTop: desktopNavTopInset,
  },
  navbar: {
    alignItems: 'center',
    flexDirection: 'row',
    height: desktopNavBarHeight,
    paddingRight: desktopWindowInset,
  },
  trafficLights: {
    height: desktopTrafficLightButton,
    marginLeft: desktopTrafficLightLeading,
    width: desktopTrafficLightRowWidth,
  },
  navItems: {alignItems: 'center', flexDirection: 'row', flexShrink: 0, gap: 4},
  navItem: {
    alignItems: 'center',
    borderRadius: 15,
    flexDirection: 'row',
    gap: 6,
    height: 30,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  navText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.nav,
    fontWeight: '600',
  },
  navTextActive: {color: token.color.ink},
  utilityButton: {
    alignItems: 'center',
    borderRadius: 16,
    height: 32,
    justifyContent: 'center',
    padding: 8,
    width: 32,
  },
  page: {flex: 1, gap: 8},
  omnibar: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 32,
    paddingHorizontal: 8,
  },
  omnibarInput: {
    color: token.color.ink,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.search,
    fontWeight: '400',
    paddingVertical: 6,
  },
  omnibarError: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    paddingHorizontal: 12,
  },
  filterRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
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
  pressed: {opacity: 0.78},
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
  stageScroll: {flex: 1},
  conversation: {gap: 4, paddingBottom: 8},
  list: {paddingBottom: 24, paddingTop: 8},
  resultRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    minHeight: 56,
  },
  glyph: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderRadius: 12,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  resultCopy: {flex: 1},
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '500',
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 2,
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
  chatRow: {gap: 4, paddingVertical: 8},
  sendButton: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.control,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  sendText: {
    color: token.color.white,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  singlePanel: {flex: 1, paddingHorizontal: 4, paddingTop: 8},
  pageTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '600',
  },
  sectionTitle: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
    marginTop: 16,
  },
  searchControl: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 32,
  },
  searchInput: {
    color: token.color.ink,
    flex: 1,
    fontFamily: token.font,
    fontSize: token.type.body,
  },
  memoryCard: {
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    marginBottom: 10,
    padding: 14,
  },
  memoryText: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.body,
    lineHeight: 21,
  },
  centerState: {
    alignItems: 'center',
    flex: 1,
    gap: 8,
    justifyContent: 'center',
  },
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  taskRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 48,
  },
  taskCircle: {
    borderColor: token.color.inkMuted,
    borderRadius: 11,
    borderWidth: 1.5,
    height: 22,
    width: 22,
  },
  taskCircleDone: {backgroundColor: token.color.ink},
  taskText: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.body,
  },
  taskTextDone: {
    color: token.color.inkFaint,
    textDecorationLine: 'line-through',
  },
  appGrid: {paddingTop: 14},
  appCard: {
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    flex: 1,
    margin: 6,
    minHeight: 108,
    padding: 12,
  },
  appCardHeader: {alignItems: 'center', flexDirection: 'row', gap: 10},
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 10,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
});
