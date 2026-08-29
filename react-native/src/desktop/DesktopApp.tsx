import React, {memo, useCallback, useMemo, useState} from 'react';
import {
  ActivityIndicator,
  FlatList,
  SectionList,
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
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import FileText from 'lucide-react-native/icons/file-text';
import Folder from 'lucide-react-native/icons/folder';
import Grid2X2 from 'lucide-react-native/icons/grid-2x2';
import History from 'lucide-react-native/icons/rotate-ccw-clock';
import Library from 'lucide-react-native/icons/library';
import ListFilter from 'lucide-react-native/icons/list-filter';
import Mic from 'lucide-react-native/icons/mic';
import Monitor from 'lucide-react-native/icons/monitor';
import MoreHorizontal from 'lucide-react-native/icons/ellipsis';
import Paperclip from 'lucide-react-native/icons/paperclip';
import Plus from 'lucide-react-native/icons/plus';
import Puzzle from 'lucide-react-native/icons/puzzle';
import Search from 'lucide-react-native/icons/search';
import Settings from 'lucide-react-native/icons/settings';
import SlidersHorizontal from 'lucide-react-native/icons/sliders-horizontal';
import Sparkles from 'lucide-react-native/icons/sparkles';
import Star from 'lucide-react-native/icons/star';
import Volume2 from 'lucide-react-native/icons/volume-2';
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

type DesktopRoute =
  | 'Home'
  | 'Library'
  | 'Tasks'
  | 'Rewind'
  | 'Apps'
  | 'Settings';
type LibraryRoute = 'Conversations' | 'Memories' | 'Brain Map';

type Props = {
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  onRefresh: () => void;
  onOpenChat: () => void;
};

const navItems: Array<{
  label: DesktopRoute;
  Icon: typeof Search;
}> = [
  {label: 'Home', Icon: Search},
  {label: 'Library', Icon: Library},
  {label: 'Tasks', Icon: ListFilter},
  {label: 'Rewind', Icon: History},
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

function Pill({
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
        styles.pill,
        active && styles.pillActive,
        pressed && styles.pressed,
      ]}>
      {Icon === undefined ? null : <Icon color={token.color.ink} size={16} />}
      <Text style={[styles.pillText, active && styles.pillTextActive]}>
        {label}
      </Text>
    </FocusPressable>
  );
}

const TimelineRow = memo(function TimelineRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
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
      : '—';
  const glyph =
    item.kind === 'conversation' ? '💬' : item.kind === 'memory' ? '🧠' : '✓';
  return (
    <View style={styles.timelineRow}>
      <Text style={styles.timelineTime}>{time}</Text>
      <View style={styles.timelineDot} />
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{glyph}</Text>
      </View>
      <View style={styles.timelineCopy}>
        <Text numberOfLines={1} style={styles.rowTitle}>
          {item.title}
        </Text>
        <Text numberOfLines={1} style={styles.rowMeta}>
          {item.kind === 'conversation'
            ? item.summary
            : item.kind === 'memory'
            ? 'Long-term memory'
            : item.completed
            ? 'Completed'
            : 'Open task'}
        </Text>
      </View>
      {item.kind === 'conversation' ? (
        <Star color={token.color.inkMuted} size={20} />
      ) : null}
    </View>
  );
});

function ReadState({
  phase,
  onRefresh,
}: {
  phase: ReadsPhase;
  onRefresh: () => void;
}) {
  if (phase === 'ready') {
    return null;
  }
  if (phase === 'initial-loading' || phase === 'refreshing') {
    return (
      <View accessibilityLabel="Timeline loading" style={styles.inlineState}>
        <ActivityIndicator color={token.color.inkMuted} size="small" />
        <Text style={styles.inlineStateText}>
          {phase === 'refreshing' ? 'Updating timeline…' : 'Loading your day…'}
        </Text>
      </View>
    );
  }
  return (
    <FocusPressable
      accessibilityLabel="Timeline offline. Try again"
      accessibilityRole="button"
      onPress={onRefresh}
      style={({pressed}) => [styles.inlineState, pressed && styles.pressed]}>
      <Text style={styles.inlineStateText}>
        Offline · showing what is available on this Mac
      </Text>
      <Text style={styles.inlineStateAction}>Try again</Text>
    </FocusPressable>
  );
}

function HomePage({
  reads,
  readsPhase,
  onOpenChat,
  onRefresh,
}: Omit<Props, 'outcomes'>) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<
    'All' | 'Conversations' | 'Memories' | 'Rewind'
  >('All');
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return reads.filter(item => {
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
  }, [filter, query, reads]);
  const sections = useMemo(
    () => [{title: 'TODAY', data: filtered}],
    [filtered],
  );
  return (
    <View style={styles.page}>
      <GlassSurface style={styles.omnisearch}>
        <Search color={token.color.inkMuted} size={25} />
        <TextInput
          accessibilityLabel="Search what you have seen and heard"
          onChangeText={setQuery}
          placeholder="Search what you've seen and heard…"
          placeholderTextColor={token.color.inkMuted}
          style={styles.omnisearchInput}
          value={query}
        />
        <Paperclip color={token.color.inkMuted} size={23} />
        <Mic color={token.color.inkMuted} size={23} />
        <FocusPressable
          accessibilityLabel="Ask Omi"
          onPress={onOpenChat}
          style={styles.sendButton}>
          <Sparkles color={token.color.white} size={21} />
        </FocusPressable>
      </GlassSurface>
      <GlassSurface style={styles.homePanel}>
        <View style={styles.filterBar}>
          <View style={styles.filterActions}>
            <ListFilter color={token.color.ink} size={18} />
            <Text style={styles.filterLabel}>Filter</Text>
            <Pill Icon={Sparkles} label="Brain Map" />
            <Pill Icon={FileText} label="Chat" onPress={onOpenChat} />
          </View>
          <Text style={styles.keptCount}>
            {reads.length} items Omi has kept
          </Text>
        </View>
        <View style={styles.filterChips}>
          {(['All', 'Conversations', 'Memories', 'Rewind'] as const).map(
            label => (
              <Pill
                active={filter === label}
                key={label}
                label={label}
                onPress={() => setFilter(label)}
              />
            ),
          )}
        </View>
        <View style={styles.timelineLayout}>
          <View style={styles.dayRail}>
            <Text style={styles.momentCount}>0</Text>
            <Text style={styles.dayRailLabel}>screen moments</Text>
            <Text style={styles.dayRailLabel}>Today</Text>
            <View style={styles.hourMarks}>
              {Array.from({length: 13}, (_, index) => (
                <View
                  key={index}
                  style={[
                    styles.hourMark,
                    index === 3 && styles.hourMarkActive,
                  ]}
                />
              ))}
            </View>
            <Text style={styles.dayRailCount}>
              {filtered.filter(item => item.kind === 'conversation').length}{' '}
              conversations
            </Text>
          </View>
          <SectionList
            contentContainerStyle={styles.timelineList}
            sections={sections}
            keyExtractor={item => `${item.kind}-${item.id}`}
            renderItem={({item}) => <TimelineRow item={item} />}
            renderSectionHeader={({section}) => (
              <View style={styles.dayHeader}>
                <Text style={styles.dayHeaderTitle}>{section.title}</Text>
                <Text style={styles.dayHeaderCount}>
                  {section.data.length} saved items
                </Text>
                <ChevronDown
                  color={token.color.inkMuted}
                  size={19}
                  style={styles.dayHeaderChevron}
                />
              </View>
            )}
            ListHeaderComponent={
              <ReadState onRefresh={onRefresh} phase={readsPhase} />
            }
            ListEmptyComponent={
              readsPhase === 'ready' ? (
                <View
                  accessibilityLabel="Empty timeline"
                  style={styles.timelineEmpty}>
                  <Text style={styles.emptyTitle}>
                    {query === '' ? 'Your day is clear' : 'No matches'}
                  </Text>
                  <Text style={styles.emptyCopy}>
                    {query === ''
                      ? 'Conversations, memories, and screen moments will collect here.'
                      : 'Try a broader search or another filter.'}
                  </Text>
                </View>
              ) : null
            }
            stickySectionHeadersEnabled={false}
          />
        </View>
      </GlassSurface>
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
    <View style={styles.libraryRow}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>💬</Text>
      </View>
      <View style={styles.timelineCopy}>
        <Text style={styles.rowTitle}>{item.title}</Text>
        <Text style={styles.rowMeta}>
          {time} · {item.summary}
        </Text>
      </View>
      <Star
        color={token.color.inkMuted}
        fill={item.starred ? token.color.inkMuted : 'transparent'}
        size={19}
      />
    </View>
  );
});

const MemoryRow = memo(function MemoryRow({item}: {item: MemoryProjection}) {
  const provenance = item.provenance.label ?? 'Omi synthesis';
  return (
    <View style={styles.memoryCard}>
      <Text numberOfLines={3} style={styles.memoryText}>
        {item.summary}
      </Text>
      <View style={styles.memoryMeta}>
        <Text style={styles.rowMeta}>
          {item.timestamp === null
            ? 'Date unavailable'
            : new Date(item.timestamp * 1000).toLocaleDateString()}
        </Text>
        <View style={styles.provenanceTag}>
          <Text style={styles.provenanceText}>{provenance}</Text>
        </View>
        <MoreHorizontal color={token.color.inkMuted} size={18} />
      </View>
    </View>
  );
});

function LibraryPage({outcomes}: {outcomes: DesktopReadOutcomes | null}) {
  const [tab, setTab] = useState<LibraryRoute>('Conversations');
  const [query, setQuery] = useState('');
  const conversations =
    outcomes?.conversations.status === 'success'
      ? outcomes.conversations.value.items
      : [];
  const memories =
    outcomes?.memories.status === 'success'
      ? outcomes.memories.value.items
      : [];
  const normalized = query.trim().toLocaleLowerCase();
  const conversationRows = conversations.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  const memoryRows = memories.filter(
    item =>
      normalized === '' ||
      item.searchableText.toLocaleLowerCase().includes(normalized),
  );
  return (
    <GlassSurface style={styles.singlePanel}>
      <View style={styles.segmented}>
        {(['Conversations', 'Memories', 'Brain Map'] as const).map(label => (
          <Pill
            active={tab === label}
            key={label}
            label={label}
            onPress={() => setTab(label)}
          />
        ))}
      </View>
      <View style={styles.libraryHeading}>
        <View>
          <Text style={styles.pageTitle}>{tab}</Text>
          <Text style={styles.pageSubtitle}>
            {tab === 'Conversations'
              ? 'Recordings, notes, and transcripts from your day'
              : tab === 'Memories'
              ? 'What Omi has learned and saved for you'
              : 'Connections across your saved context'}
          </Text>
        </View>
        <View style={styles.headingActions}>
          <Pill Icon={CheckCircle2} label="Select" />
          <Pill Icon={FileText} label="Quick Note" />
        </View>
      </View>
      <View style={styles.librarySearchRow}>
        <View style={styles.searchControl}>
          <Search color={token.color.inkMuted} size={20} />
          <TextInput
            onChangeText={setQuery}
            placeholder={`Search ${tab.toLocaleLowerCase()}`}
            placeholderTextColor={token.color.inkFaint}
            style={styles.searchInput}
            value={query}
          />
        </View>
        <Pill Icon={Star} label="Starred" />
        <Pill Icon={CalendarDays} label="Date" />
      </View>
      {tab === 'Conversations' ? (
        <FlatList
          contentContainerStyle={styles.libraryList}
          data={conversationRows}
          keyExtractor={item => item.id}
          ListHeaderComponent={
            <>
              <View style={styles.tagRow}>
                {['All', 'Starred', 'Work', 'Personal', 'Social'].map(
                  (label, index) => (
                    <Pill active={index === 0} key={label} label={label} />
                  ),
                )}
                <Pill Icon={Plus} label="" />
              </View>
              <Text style={styles.sectionTitle}>Today</Text>
            </>
          }
          ListEmptyComponent={
            <Text style={styles.emptyCopy}>No conversations in this view.</Text>
          }
          renderItem={({item}) => <ConversationRow item={item} />}
        />
      ) : tab === 'Memories' ? (
        <FlatList
          contentContainerStyle={styles.libraryList}
          data={memoryRows}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <Text style={styles.emptyCopy}>No memories in this view.</Text>
          }
          renderItem={({item}) => <MemoryRow item={item} />}
        />
      ) : (
        <View style={styles.centerState}>
          <Grid2X2 color={token.color.inkMuted} size={40} />
          <Text style={styles.emptyTitle}>Brain Map</Text>
          <Text style={styles.emptyCopy}>
            Explore relationships across the context Omi has saved.
          </Text>
        </View>
      )}
    </GlassSurface>
  );
}

const TaskRow = memo(function TaskRow({item}: {item: TaskProjection}) {
  return (
    <View style={styles.taskRow}>
      <View
        style={[styles.taskCircle, item.completed && styles.taskCircleDone]}>
        {item.completed ? <Text style={styles.taskCheck}>✓</Text> : null}
      </View>
      <Text style={[styles.taskText, item.completed && styles.taskTextDone]}>
        {item.title}
      </Text>
    </View>
  );
});

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
          <Search color={token.color.inkMuted} size={20} />
          <TextInput
            onChangeText={setQuery}
            placeholder="Search tasks…"
            placeholderTextColor={token.color.inkFaint}
            style={styles.searchInput}
            value={query}
          />
        </View>
        <Pill Icon={CheckCircle2} label="Select" />
        <FocusPressable style={styles.addButton}>
          <Plus color={token.color.white} size={22} />
        </FocusPressable>
      </View>
      <View style={styles.taskSectionHeader}>
        <Text style={styles.sectionTitle}>☀ Today</Text>
        <Text style={styles.rowMeta}>{visible.length} open</Text>
      </View>
      <FlatList
        contentContainerStyle={styles.taskList}
        data={visible}
        keyExtractor={item => item.id}
        ListEmptyComponent={
          <Text style={styles.emptyCopy}>No tasks scheduled for today.</Text>
        }
        renderItem={({item}) => <TaskRow item={item} />}
      />
      <View style={styles.shortcutBar}>
        {[
          '↑ ↓  Navigate',
          '⌘N  New',
          '⌘D  Delete',
          '⇥  Indent',
          '⇧⇥  Outdent',
        ].map(label => (
          <Text key={label} style={styles.shortcut}>
            {label}
          </Text>
        ))}
      </View>
    </GlassSurface>
  );
}

function RewindPage() {
  return (
    <View style={styles.page}>
      <GlassSurface style={styles.rewindSearch}>
        <Text style={styles.rewindTitle}>Rewind</Text>
        <History color={token.color.ink} size={28} />
        <Text style={styles.rewindPrompt}>
          Search what you've seen and heard…
        </Text>
        <Settings color={token.color.inkMuted} size={19} />
        <Switch value />
      </GlassSurface>
      <GlassSurface style={styles.rewindViewer}>
        <View style={styles.frameViewer}>
          <Monitor color={token.color.inkFaint} size={76} />
          <Text style={styles.emptyTitle}>
            Screen history is ready when capture is on
          </Text>
          <Text style={styles.emptyCopy}>
            Captured frames stay navigable by time and application.
          </Text>
        </View>
        <View style={styles.rewindTrack}>
          <View style={styles.rewindTrackFill} />
        </View>
        <View style={styles.rewindTicks}>
          {['12:30', '12:45', '1:00', '1:15', '1:30', '1:45', '2:00'].map(
            time => (
              <Text key={time} style={styles.rowMeta}>
                {time}
              </Text>
            ),
          )}
        </View>
      </GlassSurface>
    </View>
  );
}

const imports = [
  [
    'Calendar',
    'Google Calendar',
    'Import events and recurring routines.',
    CalendarDays,
  ],
  ['Email', 'Gmail', 'Import email history and follow-ups.', Archive],
  [
    'Local files',
    'This Mac',
    'Index documents, code, and working folders.',
    Folder,
  ],
  [
    'Apple Notes',
    'Private notes',
    'Import notes and private written context.',
    FileText,
  ],
  [
    'X (Twitter)',
    'Your posts & bookmarks',
    'Connect your account so Omi learns from your posts.',
    Sparkles,
  ],
  ['ChatGPT', 'Memory import', 'Bring your memory export into Omi.', Puzzle],
] as const;

function AppsPage() {
  return (
    <GlassSurface style={styles.singlePanel}>
      <View style={styles.appsSearch}>
        <View style={styles.searchControl}>
          <Search color={token.color.inkMuted} size={20} />
          <Text style={styles.searchPlaceholder}>Search apps…</Text>
        </View>
        <Pill Icon={CheckCircle2} label="Installed" />
        <Pill Icon={SlidersHorizontal} label="All Categories" />
        <Pill Icon={Plus} label="Create App" />
      </View>
      <Text style={styles.pageTitle}>Imports</Text>
      <FlatList
        contentContainerStyle={styles.appGrid}
        data={imports}
        keyExtractor={item => item[0]}
        numColumns={3}
        renderItem={({item: [name, source, copy, Icon]}) => (
          <View style={styles.appCard}>
            <View style={styles.appCardHeader}>
              <View style={styles.appIcon}>
                <Icon color={token.color.ink} size={26} />
              </View>
              <View>
                <Text style={styles.rowTitle}>{name}</Text>
                <Text style={styles.rowMeta}>{source}</Text>
              </View>
            </View>
            <Text style={styles.appCopy}>{copy}</Text>
            <View style={styles.appFooter}>
              <Text style={styles.rowMeta}>Not connected</Text>
              <View style={styles.connectButton}>
                <Text style={styles.connectText}>Connect</Text>
              </View>
            </View>
          </View>
        )}
      />
    </GlassSurface>
  );
}

function SettingRow({
  Icon,
  title,
  copy,
  enabled,
  onChange,
}: {
  Icon: typeof Search;
  title: string;
  copy: string;
  enabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingIcon}>
        <Icon color={token.color.ink} size={22} />
      </View>
      <View style={styles.timelineCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowMeta}>{copy}</Text>
      </View>
      <Switch onValueChange={onChange} value={enabled} />
    </View>
  );
}

function SettingsPage() {
  const [screenCapture, setScreenCapture] = useState(false);
  const [audio, setAudio] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [sounds, setSounds] = useState(true);
  return (
    <GlassSurface style={styles.singlePanel}>
      <Text style={styles.pageTitle}>General</Text>
      <View style={styles.settingsList}>
        <SettingRow
          Icon={Monitor}
          copy={
            screenCapture
              ? 'Screen capture is active'
              : 'Screen capture is paused'
          }
          enabled={screenCapture}
          onChange={setScreenCapture}
          title="Screen Capture"
        />
        <SettingRow
          Icon={Mic}
          copy={
            audio ? 'Audio recording is active' : 'Audio recording is paused'
          }
          enabled={audio}
          onChange={setAudio}
          title="Audio Recording"
        />
        <SettingRow
          Icon={Bell}
          copy={
            notifications
              ? 'Notifications are enabled'
              : 'Notifications are disabled'
          }
          enabled={notifications}
          onChange={setNotifications}
          title="Notifications"
        />
        <View style={styles.settingRow}>
          <View style={styles.settingIcon}>
            <Volume2 color={token.color.ink} size={22} />
          </View>
          <View style={styles.timelineCopy}>
            <Text style={styles.rowTitle}>System Audio</Text>
            <Text style={styles.rowMeta}>
              Choose when Omi records audio from other apps.
            </Text>
          </View>
          <Pill Icon={ChevronDown} label="Never" />
        </View>
        <SettingRow
          Icon={Volume2}
          copy="Clicks and chimes as you move around Omi."
          enabled={sounds}
          onChange={setSounds}
          title="Interface Sounds"
        />
      </View>
    </GlassSurface>
  );
}

export function DesktopApp({
  outcomes,
  reads,
  readsPhase,
  onOpenChat,
  onRefresh,
}: Props) {
  const [route, setRoute] = useState<DesktopRoute>('Home');
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
              <Icon color={token.color.ink} size={19} />
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
          <Mic color={token.color.inkMuted} size={20} />
          <Monitor color={token.color.inkMuted} size={20} />
          <FocusPressable
            accessibilityLabel="Settings"
            onPress={() => navigate('Settings')}
            style={({pressed}) => [
              styles.utilityButton,
              route === 'Settings' && styles.navItemActive,
              pressed && styles.pressed,
            ]}>
            <Settings color={token.color.ink} size={20} />
          </FocusPressable>
        </View>
      </GlassSurface>
      {route === 'Home' ? (
        <HomePage
          onOpenChat={onOpenChat}
          onRefresh={onRefresh}
          reads={reads}
          readsPhase={readsPhase}
        />
      ) : route === 'Library' ? (
        <LibraryPage outcomes={outcomes} />
      ) : route === 'Tasks' ? (
        <TasksPage outcomes={outcomes} />
      ) : route === 'Rewind' ? (
        <RewindPage />
      ) : route === 'Apps' ? (
        <AppsPage />
      ) : (
        <SettingsPage />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'rgba(99, 177, 214, 0.56)',
    flex: 1,
    padding: 16,
    gap: 14,
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
    height: 66,
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  navItems: {alignItems: 'center', flexDirection: 'row', gap: 6},
  navItem: {
    alignItems: 'center',
    borderRadius: token.radius.pill,
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  navItemActive: {backgroundColor: token.color.glassSelected},
  navText: {color: token.color.inkMuted, fontSize: 15, fontWeight: '600'},
  navTextActive: {color: token.color.ink, fontWeight: '700'},
  navUtilities: {alignItems: 'center', flexDirection: 'row', gap: 18},
  utilityButton: {borderRadius: token.radius.pill, padding: 9},
  page: {flex: 1, gap: 14},
  omnisearch: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    minHeight: 82,
    paddingHorizontal: 22,
  },
  omnisearchInput: {
    color: token.color.ink,
    flex: 1,
    fontSize: token.type.hero,
    fontWeight: '600',
    paddingVertical: 18,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: token.color.inkFaint,
    borderRadius: 25,
    height: 50,
    justifyContent: 'center',
    width: 50,
  },
  homePanel: {flex: 1, padding: 18},
  filterBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  filterActions: {alignItems: 'center', flexDirection: 'row', gap: 10},
  filterLabel: {color: token.color.ink, fontSize: 16, fontWeight: '600'},
  keptCount: {color: token.color.inkMuted, fontSize: token.type.meta},
  filterChips: {flexDirection: 'row', gap: 8, marginTop: 14},
  pill: {
    alignItems: 'center',
    borderColor: token.color.line,
    borderRadius: token.radius.pill,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 7,
    minHeight: 34,
    paddingHorizontal: 13,
  },
  pillActive: {
    backgroundColor: token.color.glassSelected,
    borderColor: token.color.lineStrong,
  },
  pillText: {color: token.color.inkMuted, fontSize: 14, fontWeight: '600'},
  pillTextActive: {color: token.color.ink, fontWeight: '700'},
  pressed: {opacity: 0.66},
  timelineLayout: {flex: 1, flexDirection: 'row', marginTop: 15},
  dayRail: {
    borderRightColor: token.color.line,
    borderRightWidth: 1,
    padding: 14,
    width: 210,
  },
  momentCount: {color: token.color.ink, fontSize: 30, fontWeight: '700'},
  dayRailLabel: {color: token.color.inkMuted, fontSize: 14, marginTop: 3},
  hourMarks: {gap: 7, marginVertical: 18},
  hourMark: {
    backgroundColor: 'rgba(69, 107, 126, 0.32)',
    borderRadius: 3,
    height: 5,
    width: 18,
  },
  hourMarkActive: {backgroundColor: token.color.ink, width: 22},
  dayRailCount: {color: token.color.inkMuted, fontSize: 13},
  timelineList: {paddingBottom: 28, paddingLeft: 14},
  dayHeader: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderRadius: 13,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 44,
    paddingHorizontal: 16,
  },
  dayHeaderTitle: {
    color: token.color.ink,
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 1.4,
  },
  dayHeaderCount: {color: token.color.inkMuted, fontSize: 14, marginLeft: 14},
  dayHeaderChevron: {marginLeft: 'auto'},
  timelineRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    minHeight: 86,
    paddingHorizontal: 12,
  },
  timelineTime: {
    color: token.color.inkMuted,
    fontSize: 14,
    textAlign: 'right',
    width: 64,
  },
  timelineDot: {
    backgroundColor: token.color.inkMuted,
    borderRadius: 4,
    height: 7,
    width: 7,
  },
  avatar: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 22,
    borderWidth: 1,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  avatarText: {fontSize: 21},
  timelineCopy: {flex: 1},
  rowTitle: {color: token.color.ink, fontSize: 16, fontWeight: '700'},
  rowMeta: {color: token.color.inkMuted, fontSize: 13, marginTop: 3},
  inlineState: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderRadius: 12,
    flexDirection: 'row',
    gap: 8,
    marginBottom: 8,
    minHeight: 38,
    paddingHorizontal: 12,
  },
  inlineStateText: {color: token.color.inkMuted, fontSize: 13},
  inlineStateAction: {
    color: token.color.ink,
    fontSize: 13,
    fontWeight: '700',
    marginLeft: 'auto',
  },
  timelineEmpty: {padding: 34},
  emptyTitle: {
    color: token.color.ink,
    fontSize: 18,
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
  singlePanel: {flex: 1, padding: 26},
  segmented: {
    alignSelf: 'flex-start',
    backgroundColor: token.color.glassQuiet,
    borderRadius: token.radius.pill,
    flexDirection: 'row',
    padding: 5,
  },
  libraryHeading: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 24,
  },
  pageTitle: {
    color: token.color.ink,
    fontSize: token.type.title,
    fontWeight: '700',
  },
  pageSubtitle: {color: token.color.inkMuted, fontSize: 14, marginTop: 5},
  headingActions: {flexDirection: 'row', gap: 8},
  librarySearchRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    marginTop: 24,
  },
  searchControl: {
    alignItems: 'center',
    borderColor: token.color.line,
    borderRadius: token.radius.control,
    borderWidth: 1,
    flex: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 48,
    paddingHorizontal: 15,
  },
  searchInput: {color: token.color.ink, flex: 1, fontSize: 15},
  searchPlaceholder: {color: token.color.inkFaint, fontSize: 15},
  libraryList: {paddingBottom: 32, paddingTop: 18},
  tagRow: {flexDirection: 'row', gap: 8, marginBottom: 28},
  sectionTitle: {color: token.color.ink, fontSize: 17, fontWeight: '700'},
  libraryRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    minHeight: 76,
    paddingHorizontal: 14,
  },
  memoryCard: {
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 12,
    padding: 18,
  },
  memoryText: {color: token.color.ink, fontSize: 16, lineHeight: 23},
  memoryMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    marginTop: 12,
  },
  provenanceTag: {
    backgroundColor: token.color.glassSelected,
    borderRadius: token.radius.pill,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  provenanceText: {
    color: token.color.inkMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  centerState: {alignItems: 'center', flex: 1, justifyContent: 'center'},
  tasksHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  addButton: {
    alignItems: 'center',
    backgroundColor: token.color.dark,
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  taskSectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 28,
  },
  taskList: {paddingBottom: 80, paddingTop: 14},
  taskRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 16,
    minHeight: 66,
    paddingHorizontal: 22,
  },
  taskCircle: {
    borderColor: token.color.inkMuted,
    borderRadius: 13,
    borderWidth: 2,
    height: 26,
    width: 26,
  },
  taskCircleDone: {
    alignItems: 'center',
    backgroundColor: token.color.ink,
    justifyContent: 'center',
  },
  taskCheck: {color: token.color.white, fontSize: 14, fontWeight: '700'},
  taskText: {color: token.color.ink, fontSize: 16},
  taskTextDone: {
    color: token.color.inkFaint,
    textDecorationLine: 'line-through',
  },
  shortcutBar: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderRadius: token.radius.pill,
    borderWidth: 1,
    bottom: 18,
    flexDirection: 'row',
    gap: 18,
    paddingHorizontal: 18,
    paddingVertical: 12,
    position: 'absolute',
  },
  shortcut: {color: token.color.inkMuted, fontSize: 12},
  rewindSearch: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 16,
    minHeight: 84,
    paddingHorizontal: 24,
  },
  rewindTitle: {color: token.color.ink, fontSize: 20, fontWeight: '700'},
  rewindPrompt: {
    color: token.color.inkFaint,
    flex: 1,
    fontSize: 24,
    fontWeight: '600',
  },
  rewindViewer: {flex: 1, padding: 20},
  frameViewer: {
    alignItems: 'center',
    backgroundColor: 'rgba(15, 25, 32, 0.82)',
    borderRadius: 18,
    flex: 1,
    justifyContent: 'center',
  },
  rewindTrack: {
    backgroundColor: token.color.glassQuiet,
    borderRadius: 8,
    height: 26,
    marginTop: 18,
    overflow: 'hidden',
  },
  rewindTrackFill: {backgroundColor: '#188c52', height: '100%', width: '76%'},
  rewindTicks: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  appsSearch: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    marginBottom: 28,
  },
  appGrid: {paddingTop: 18},
  appCard: {
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 17,
    borderWidth: 1,
    flex: 1,
    margin: 7,
    minHeight: 175,
    padding: 16,
  },
  appCardHeader: {alignItems: 'center', flexDirection: 'row', gap: 12},
  appIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderColor: token.color.line,
    borderRadius: 13,
    borderWidth: 1,
    height: 50,
    justifyContent: 'center',
    width: 50,
  },
  appCopy: {
    color: token.color.inkMuted,
    fontSize: 13,
    lineHeight: 18,
    marginTop: 16,
  },
  appFooter: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 'auto',
  },
  connectButton: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.pill,
    paddingHorizontal: 15,
    paddingVertical: 8,
  },
  connectText: {color: token.color.white, fontSize: 13, fontWeight: '700'},
  settingsList: {gap: 18, marginTop: 28},
  settingRow: {
    alignItems: 'center',
    backgroundColor: token.color.glassQuiet,
    borderColor: token.color.line,
    borderRadius: 17,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 16,
    minHeight: 92,
    padding: 18,
  },
  settingIcon: {
    alignItems: 'center',
    backgroundColor: token.color.glassStrong,
    borderRadius: 10,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
});
