import React, {memo, useCallback, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import Bell from 'lucide-react-native/icons/bell';
import CalendarDays from 'lucide-react-native/icons/calendar-days';
import CheckCircle2 from 'lucide-react-native/icons/circle-check';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Grid2X2 from 'lucide-react-native/icons/grid-2x2';
import Library from 'lucide-react-native/icons/library';
import ListFilter from 'lucide-react-native/icons/list-filter';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Mic from 'lucide-react-native/icons/mic';
import Monitor from 'lucide-react-native/icons/monitor';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Settings from 'lucide-react-native/icons/settings';
import Sparkles from 'lucide-react-native/icons/sparkles';
import Volume2 from 'lucide-react-native/icons/volume-2';
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
import {GlassPanel} from '../ui/GlassPanel';
import {desktopTokens as token} from './tokens';

export type DesktopSession = 'probing' | 'signed-out' | 'ready';
type DesktopRoute = 'Chat' | 'Memories' | 'Tasks' | 'Apps' | 'Settings';
type MemoryHub =
  'Activity' | 'Conversations' | 'Memories' | 'Rewind' | 'Brain Map';

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

const navItems: Array<{
  label: Exclude<DesktopRoute, 'Settings'>;
  Icon: typeof Search;
}> = [
  {label: 'Chat', Icon: MessageCircle},
  {label: 'Memories', Icon: Library},
  {label: 'Tasks', Icon: ListFilter},
  {label: 'Apps', Icon: Puzzle},
];

function GlassSurface({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: object;
}) {
  return (
    <View style={[styles.glassSurface, style]}>
      <GlassPanel
        glassCornerRadius={token.radius.panel}
        pointerEvents="none"
        style={StyleSheet.absoluteFill}
      />
      {children}
    </View>
  );
}

function Chip({
  active = false,
  Icon,
  label,
  onPress,
}: {
  active?: boolean;
  Icon?: typeof Search;
  label: string;
  onPress?: () => void;
}) {
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.chip,
        active && styles.chipActive,
        pressed && styles.pressed,
      ]}>
      {Icon === undefined ? null : <Icon color={token.color.ink} size={16} />}
      <Text style={[styles.chipText, active && styles.chipTextActive]}>
        {label}
      </Text>
    </FocusPressable>
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
        <Icon color={token.color.ink} size={18} />
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
        <MessageCircle color={token.color.ink} size={18} />
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

function ChatHome({
  chatBusy,
  chatError,
  draft,
  messages,
  onDraftChange,
  onSend,
  onSignIn,
  onRefresh,
  reads,
  readsPhase,
  session,
  signingIn,
}: Props) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<
    'All' | 'Conversations' | 'Memories' | 'Tasks' | 'Rewind'
  >('All');
  const searching = query.trim() !== '';
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return reads.filter(item => {
      const kindMatches =
        filter === 'All' ||
        (filter === 'Conversations' && item.kind === 'conversation') ||
        (filter === 'Memories' && item.kind === 'memory') ||
        (filter === 'Tasks' && item.kind === 'task');
      return (
        kindMatches &&
        (normalized === '' ||
          item.searchableText.toLocaleLowerCase().includes(normalized))
      );
    });
  }, [filter, query, reads]);
  return (
    <View style={styles.page}>
      <GlassSurface style={styles.omnisearch}>
        <Search color={token.color.inkMuted} size={22} />
        <TextInput
          accessibilityLabel="Search what you have seen and heard"
          onChangeText={setQuery}
          placeholder="Search what you've seen and heard…"
          placeholderTextColor={token.color.inkMuted}
          style={styles.omnisearchInput}
          value={query}
        />
      </GlassSurface>
      <GlassSurface style={styles.homePanel}>
        <View style={styles.filterBar}>
          <Text style={styles.filterLabel}>Filter</Text>
          <View style={styles.filterChips}>
            {(
              ['All', 'Conversations', 'Memories', 'Tasks', 'Rewind'] as const
            ).map(label => (
              <Chip
                active={filter === label}
                key={label}
                label={label}
                onPress={() => setFilter(label)}
              />
            ))}
          </View>
        </View>
        <SessionBanner
          onRefresh={onRefresh}
          onSignIn={onSignIn}
          readsPhase={readsPhase}
          session={session}
          signingIn={signingIn}
        />
        {searching ? (
          <FlatList
            contentContainerStyle={styles.list}
            data={filtered}
            keyExtractor={item => `${item.kind}-${item.id}`}
            ListEmptyComponent={
              readsPhase === 'ready' ? (
                <Text style={styles.emptyCopy}>
                  Nothing captured matches this search.
                </Text>
              ) : null
            }
            renderItem={({item}) => <ResultRow item={item} />}
          />
        ) : (
          <View style={styles.chatStage}>
            {messages.length === 0 && !chatBusy ? (
              <View style={styles.resting}>
                <Text style={styles.emptyTitle}>I'm ready.</Text>
              </View>
            ) : (
              <FlatList
                contentContainerStyle={styles.list}
                data={messages}
                keyExtractor={item => item.id}
                renderItem={({item}) => (
                  <View style={styles.chatRow}>
                    <Text style={styles.rowMeta}>
                      {item.sender === 'human' ? 'You' : 'Omi'}
                    </Text>
                    <Text style={styles.rowTitle}>{item.text}</Text>
                  </View>
                )}
              />
            )}
            {chatError !== null ? (
              <Text style={styles.errorText}>{chatError}</Text>
            ) : null}
            <View style={styles.composer}>
              <TextInput
                accessibilityLabel="Ask a follow-up"
                onChangeText={onDraftChange}
                onSubmitEditing={onSend}
                placeholder="Ask a follow-up…"
                placeholderTextColor={token.color.inkFaint}
                style={styles.composerInput}
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
          </View>
        )}
      </GlassSurface>
    </View>
  );
}

function MemoriesPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
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
    <GlassSurface style={styles.singlePanel}>
      <View style={styles.hubRow}>
        {(
          [
            'Activity',
            'Conversations',
            'Memories',
            'Rewind',
            'Brain Map',
          ] as const
        ).map(label => (
          <Chip
            active={hub === label}
            key={label}
            label={label}
            onPress={() => setHub(label)}
          />
        ))}
      </View>
      {hub === 'Conversations' ? (
        <FlatList
          contentContainerStyle={styles.list}
          data={conversations}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          }
          renderItem={({item}) => <ConversationRow item={item} />}
        />
      ) : hub === 'Memories' ? (
        <FlatList
          contentContainerStyle={styles.list}
          data={memories}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          }
          renderItem={({item}) => <MemoryRow item={item} />}
        />
      ) : hub === 'Rewind' ? (
        <View style={styles.centerState}>
          <Monitor color={token.color.inkMuted} size={36} />
          <Text style={styles.emptyTitle}>
            Screen history is ready when capture is on
          </Text>
          <Text style={styles.emptyCopy}>
            Captured frames stay navigable by time and application.
          </Text>
        </View>
      ) : hub === 'Brain Map' ? (
        <View style={styles.centerState}>
          <Grid2X2 color={token.color.inkMuted} size={36} />
          <Text style={styles.emptyTitle}>No connections to show yet.</Text>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.list}
          data={conversations}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <Text style={styles.emptyCopy}>
              Nothing captured in this window yet.
            </Text>
          }
          ListHeaderComponent={
            <Text style={styles.sectionTitle}>Activity</Text>
          }
          renderItem={({item}) => <ConversationRow item={item} />}
        />
      )}
    </GlassSurface>
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
    <GlassSurface style={styles.singlePanel}>
      <View style={styles.tasksHeader}>
        <Text style={styles.pageTitle}>Tasks</Text>
        <View style={styles.searchControl}>
          <Search color={token.color.inkMuted} size={18} />
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
      <FlatList
        contentContainerStyle={styles.list}
        data={visible}
        keyExtractor={item => item.id}
        ListEmptyComponent={<Text style={styles.emptyCopy}>No tasks yet</Text>}
        renderItem={({item}) => <TaskRow item={item} />}
      />
    </GlassSurface>
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
    <GlassSurface style={styles.singlePanel}>
      <Text style={styles.pageTitle}>Imports</Text>
      <FlatList
        contentContainerStyle={styles.appGrid}
        data={imports}
        keyExtractor={item => item[0]}
        numColumns={3}
        renderItem={({item: [name, source, Icon]}) => (
          <View style={styles.appCard}>
            <View style={styles.appCardHeader}>
              <View style={styles.appIcon}>
                <Icon color={token.color.ink} size={22} />
              </View>
              <View>
                <Text style={styles.rowTitle}>{name}</Text>
                <Text style={styles.rowMeta}>{source}</Text>
              </View>
            </View>
            <Text style={styles.rowMeta}>Not connected</Text>
          </View>
        )}
      />
    </GlassSurface>
  );
}

function SettingsPage({
  session,
  signingIn,
  onSignIn,
  onSignOut,
}: {
  session: DesktopSession;
  signingIn: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  const [screenCapture, setScreenCapture] = useState(false);
  const [audio, setAudio] = useState(false);
  const [notifications, setNotifications] = useState(false);
  return (
    <GlassSurface style={styles.singlePanel}>
      <Text style={styles.pageTitle}>General</Text>
      <View style={styles.settingsList}>
        <View style={styles.settingRow}>
          <View style={styles.settingIcon}>
            <Monitor color={token.color.ink} size={20} />
          </View>
          <View style={styles.resultCopy}>
            <Text style={styles.rowTitle}>Screen Capture</Text>
            <Text style={styles.rowMeta}>
              {screenCapture
                ? 'Screen capture is active'
                : 'Screen capture is paused'}
            </Text>
          </View>
          <Switch onValueChange={setScreenCapture} value={screenCapture} />
        </View>
        <View style={styles.settingRow}>
          <View style={styles.settingIcon}>
            <Mic color={token.color.ink} size={20} />
          </View>
          <View style={styles.resultCopy}>
            <Text style={styles.rowTitle}>Audio Recording</Text>
            <Text style={styles.rowMeta}>
              {audio
                ? 'Audio recording is active'
                : 'Audio recording is paused'}
            </Text>
          </View>
          <Switch onValueChange={setAudio} value={audio} />
        </View>
        <View style={styles.settingRow}>
          <View style={styles.settingIcon}>
            <Bell color={token.color.ink} size={20} />
          </View>
          <View style={styles.resultCopy}>
            <Text style={styles.rowTitle}>Notifications</Text>
            <Text style={styles.rowMeta}>
              {notifications
                ? 'Notifications are enabled'
                : 'Notifications are disabled'}
            </Text>
          </View>
          <Switch onValueChange={setNotifications} value={notifications} />
        </View>
        <View style={styles.settingRow}>
          <View style={styles.settingIcon}>
            <Volume2 color={token.color.ink} size={20} />
          </View>
          <View style={styles.resultCopy}>
            <Text style={styles.rowTitle}>Account</Text>
            <Text style={styles.rowMeta}>
              {session === 'ready'
                ? 'Signed in to Omi'
                : 'Sign in to load conversations and memories.'}
            </Text>
          </View>
          <FocusPressable
            accessibilityLabel={session === 'ready' ? 'Sign out' : 'Sign in'}
            accessibilityRole="button"
            disabled={signingIn}
            onPress={session === 'ready' ? onSignOut : onSignIn}
            style={({pressed}) => [
              styles.signInButton,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.signInText}>
              {session === 'ready'
                ? 'Sign out'
                : signingIn
                  ? 'Signing in…'
                  : 'Sign in'}
            </Text>
          </FocusPressable>
        </View>
      </View>
    </GlassSurface>
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
  const [route, setRoute] = useState<DesktopRoute>('Chat');
  const navigate = useCallback((next: DesktopRoute) => setRoute(next), []);
  return (
    <View accessibilityLabel="Omi desktop" style={styles.root}>
      <GlassSurface style={styles.navbar}>
        <View style={styles.navItems}>
          {navItems.map(({label, Icon}) => (
            <FocusPressable
              accessibilityRole="button"
              accessibilityState={{selected: route === label}}
              key={label}
              onPress={() => navigate(label)}
              style={({pressed}) => [
                styles.navItem,
                route === label && styles.navItemActive,
                pressed && styles.pressed,
              ]}>
              <Icon color={token.color.ink} size={18} />
              <Text
                style={[
                  styles.navText,
                  route === label && styles.navTextActive,
                ]}>
                {label}
              </Text>
            </FocusPressable>
          ))}
        </View>
        <View style={styles.navUtilities}>
          <Mic color={token.color.inkMuted} size={18} />
          <Monitor color={token.color.inkMuted} size={18} />
          <FocusPressable
            accessibilityLabel="Settings"
            onPress={() => navigate('Settings')}
            style={({pressed}) => [
              styles.utilityButton,
              route === 'Settings' && styles.navItemActive,
              pressed && styles.pressed,
            ]}>
            <Settings color={token.color.ink} size={18} />
          </FocusPressable>
        </View>
      </GlassSurface>
      {route === 'Chat' ? (
        <ChatHome
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
      ) : route === 'Memories' ? (
        <MemoriesPage outcomes={outcomes} />
      ) : route === 'Tasks' ? (
        <TasksPage outcomes={outcomes} />
      ) : route === 'Apps' ? (
        <AppsPage />
      ) : (
        <SettingsPage
          onSignIn={onSignIn}
          onSignOut={onSignOut}
          session={session}
          signingIn={signingIn}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'transparent',
    flex: 1,
    gap: 14,
    padding: 16,
  },
  glassSurface: {
    backgroundColor: token.color.glass,
    borderColor: token.color.line,
    borderRadius: token.radius.panel,
    borderWidth: 1,
    overflow: 'hidden',
  },
  navbar: {
    alignItems: 'center',
    flexDirection: 'row',
    height: 62,
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  navItems: {alignItems: 'center', flexDirection: 'row', gap: 6},
  navItem: {
    alignItems: 'center',
    borderRadius: token.radius.control,
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  navItemActive: {backgroundColor: token.color.glassSelected},
  navText: {color: token.color.inkMuted, fontSize: 15, fontWeight: '600'},
  navTextActive: {color: token.color.ink, fontWeight: '700'},
  navUtilities: {alignItems: 'center', flexDirection: 'row', gap: 16},
  utilityButton: {borderRadius: token.radius.control, padding: 8},
  page: {flex: 1, gap: 14},
  omnisearch: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 72,
    paddingHorizontal: 20,
  },
  omnisearchInput: {
    color: token.color.ink,
    flex: 1,
    fontSize: token.type.hero,
    fontWeight: '600',
    paddingVertical: 16,
  },
  homePanel: {flex: 1, padding: 18},
  filterBar: {gap: 10},
  filterLabel: {color: token.color.ink, fontSize: 16, fontWeight: '600'},
  filterChips: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  chip: {
    alignItems: 'center',
    borderColor: token.color.line,
    borderRadius: token.radius.chip,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    minHeight: 34,
    paddingHorizontal: 12,
  },
  chipActive: {
    backgroundColor: token.color.glassSelected,
    borderColor: token.color.lineStrong,
  },
  chipText: {color: token.color.inkMuted, fontSize: 14, fontWeight: '600'},
  chipTextActive: {color: token.color.ink, fontWeight: '700'},
  pressed: {opacity: 0.66},
  banner: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderRadius: token.radius.control,
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
    minHeight: 44,
    paddingHorizontal: 14,
  },
  bannerText: {color: token.color.inkMuted, flex: 1, fontSize: 14},
  bannerAction: {color: token.color.ink, fontSize: 14, fontWeight: '700'},
  signInButton: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.control,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  signInText: {color: token.color.white, fontSize: 13, fontWeight: '700'},
  list: {paddingBottom: 28, paddingTop: 12},
  resultRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 72,
  },
  glyph: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: token.radius.control,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  resultCopy: {flex: 1},
  rowTitle: {color: token.color.ink, fontSize: 16, fontWeight: '700'},
  rowMeta: {color: token.color.inkMuted, fontSize: 13, marginTop: 3},
  emptyTitle: {
    color: token.color.ink,
    fontSize: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyCopy: {
    color: token.color.inkMuted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
    textAlign: 'center',
  },
  chatStage: {flex: 1, marginTop: 16},
  resting: {alignItems: 'center', flex: 1, justifyContent: 'center'},
  chatRow: {gap: 4, paddingVertical: 10},
  errorText: {color: token.color.red, fontSize: 13, marginTop: 8},
  composer: {
    alignItems: 'center',
    borderColor: token.color.line,
    borderRadius: token.radius.control,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginTop: 'auto',
    minHeight: 52,
    paddingHorizontal: 14,
  },
  composerInput: {color: token.color.ink, flex: 1, fontSize: 15},
  sendButton: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.control,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  sendText: {color: token.color.white, fontSize: 13, fontWeight: '700'},
  singlePanel: {flex: 1, padding: 24},
  hubRow: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  pageTitle: {
    color: token.color.ink,
    fontSize: token.type.title,
    fontWeight: '700',
  },
  sectionTitle: {
    color: token.color.ink,
    fontSize: 17,
    fontWeight: '700',
    marginTop: 20,
  },
  searchControl: {
    alignItems: 'center',
    borderColor: token.color.line,
    borderRadius: token.radius.control,
    borderWidth: 1,
    flex: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  searchInput: {color: token.color.ink, flex: 1, fontSize: 15},
  memoryCard: {
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 12,
    padding: 16,
  },
  memoryText: {color: token.color.ink, fontSize: 16, lineHeight: 23},
  centerState: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    gap: 8,
  },
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  taskRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    minHeight: 58,
  },
  taskCircle: {
    borderColor: token.color.inkMuted,
    borderRadius: 13,
    borderWidth: 2,
    height: 26,
    width: 26,
  },
  taskCircleDone: {backgroundColor: token.color.ink},
  taskText: {color: token.color.ink, fontSize: 16},
  taskTextDone: {
    color: token.color.inkFaint,
    textDecorationLine: 'line-through',
  },
  appGrid: {paddingTop: 18},
  appCard: {
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    margin: 6,
    minHeight: 120,
    padding: 14,
  },
  appCardHeader: {alignItems: 'center', flexDirection: 'row', gap: 10},
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderRadius: 12,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  settingsList: {gap: 14, marginTop: 24},
  settingRow: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 14,
    minHeight: 80,
    padding: 16,
  },
  settingIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 10,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
});
