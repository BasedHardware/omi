import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  Easing,
  FlatList,
  Image,
  KeyboardAvoidingView,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  Pressable,
  type PressableProps,
  requireNativeComponent,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
  type ViewProps,
} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Brain from 'lucide-react-native/icons/brain';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import MessageCircle from 'lucide-react-native/icons/message-circle';
import Mic from 'lucide-react-native/icons/mic';
import PanelLeft from 'lucide-react-native/icons/panel-left';
import PanelLeftClose from 'lucide-react-native/icons/panel-left-close';
import Paperclip from 'lucide-react-native/icons/paperclip';
import Search from 'lucide-react-native/icons/search';
import Square from 'lucide-react-native/icons/square';
import {
  cancelChatGeneration,
  ChatBackendError,
  chatErrorCopy,
  createLocalChatMessage,
  loadNewestChatHistory,
  loadOlderChatHistory,
  mergeOlderChatHistory,
  reconcileCanonicalChatHistory,
  sendChatMessage,
  type ChatMessage,
} from './src/chatClient';
import {omiBackend} from './src/omiNative';
import {
  conversationGroupLabel,
  loadDesktopReads,
  loadMemories,
  taskGroup,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
  type ConversationProjection,
  type DomainReadOutcome,
  type MemoryProjection,
  type ReadPageState,
  type TaskGroup,
  type TaskProjection,
} from './src/desktopReadClient';
import {subscribeDesktopSearchCommand} from './src/desktopCommands';

type NavigationIcon = React.ComponentType<{
  accessible?: boolean;
  color?: string;
  size?: number;
  strokeWidth?: number;
}>;

const navigation: Array<{label: string; icon: NavigationIcon}> = [
  {label: 'Home', icon: House},
  {label: 'Conversations', icon: GanttChartSquare},
  {label: 'Memories', icon: Brain},
  {label: 'Tasks', icon: ListChecks},
];
const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];
const omiLogo = {
  uri: 'data:image/png;base64,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',
};
type Route = 'Home' | 'Chat' | 'Conversations' | 'Memories' | 'Tasks';
const OmiGlassPanel =
  Platform.OS === 'macos'
    ? requireNativeComponent<ViewProps>('OmiGlassPanel')
    : View;
type ProjectionFilter = 'all' | DesktopReadProjection['kind'];
type ReadsPhase =
  | 'initial-loading'
  | 'refreshing'
  | 'ready'
  | 'saved-but-refresh-failed'
  | 'unavailable';

function FocusPressable({onBlur, onFocus, style, ...props}: PressableProps) {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      {...props}
      onBlur={event => {
        setFocused(false);
        onBlur?.(event);
      }}
      onFocus={event => {
        setFocused(true);
        onFocus?.(event);
      }}
      style={state => [
        typeof style === 'function' ? style(state) : style,
        focused && styles.focusRing,
      ]}
    />
  );
}

function NavItem({
  label,
  icon: Icon,
  compact,
  active,
  expanded,
  onPress,
}: {
  label: string;
  icon: NavigationIcon;
  compact: boolean;
  active: boolean;
  expanded: boolean;
  onPress: () => void;
}) {
  return (
    <FocusPressable
      accessibilityRole="tab"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.navItem,
        compact && styles.navItemCompact,
        active && compact && styles.navItemActive,
        pressed && styles.pressed,
      ]}>
      <Icon
        accessible={false}
        color={active ? '#141414' : '#888888'}
        size={20}
        strokeWidth={2}
      />
      <Text
        numberOfLines={1}
        style={[
          styles.navText,
          !compact && !expanded && styles.navTextCollapsed,
          active && styles.navTextActive,
        ]}>
        {label}
      </Text>
    </FocusPressable>
  );
}

function OmiMark() {
  return (
    <View accessibilityLabel="Omi" style={styles.mark}>
      <Image resizeMode="contain" source={omiLogo} style={styles.markImage} />
    </View>
  );
}

function OmiAvatar() {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.chatAvatar}>
      {[
        styles.chatAvatarDotTop,
        styles.chatAvatarDotTopRight,
        styles.chatAvatarDotRight,
        styles.chatAvatarDotBottomRight,
        styles.chatAvatarDotBottom,
        styles.chatAvatarDotBottomLeft,
        styles.chatAvatarDotLeft,
        styles.chatAvatarDotTopLeft,
      ].map((position, index) => (
        <View key={index} style={[styles.chatAvatarDot, position]} />
      ))}
    </View>
  );
}

const filterLabels: Array<{label: string; value: ProjectionFilter}> = [
  {label: 'All', value: 'all'},
  {label: 'Conversations', value: 'conversation'},
  {label: 'Memories', value: 'memory'},
];

function displayTitle(item: DesktopReadProjection): string {
  return item.kind === 'memory'
    ? item.title.replace(/^entity:[^\s]+\s+/, '')
    : item.title;
}

function displaySummary(item: DesktopReadProjection): string {
  return item.kind === 'memory'
    ? 'Synthesized memory with source citations'
    : item.summary;
}

const ProjectionRow = memo(function ProjectionRow({
  item,
}: {
  item: DesktopReadProjection;
}) {
  return (
    <View style={styles.resultRow}>
      <View style={styles.resultKindRow}>
        <Text style={styles.resultKind}>{item.kind}</Text>
        {item.kind === 'conversation' && item.starred && (
          <Text style={styles.resultMeta}>Starred</Text>
        )}
      </View>
      <Text numberOfLines={2} style={styles.resultTitle}>
        {displayTitle(item)}
      </Text>
      <Text numberOfLines={2} style={styles.resultSummary}>
        {displaySummary(item)}
      </Text>
    </View>
  );
});

function ProjectionList({
  items,
  loading,
  error,
  emptyCopy,
  header,
  footer,
  emptyTitle,
  suppressEmpty,
}: {
  items: DesktopReadProjection[];
  loading: boolean;
  error: string | null;
  emptyCopy: string;
  header?: React.ReactElement;
  footer?: React.ReactElement;
  emptyTitle?: string;
  suppressEmpty?: boolean;
}) {
  const renderItem = useCallback(
    ({item}: {item: DesktopReadProjection}) => <ProjectionRow item={item} />,
    [],
  );
  const keyExtractor = useCallback(
    (item: DesktopReadProjection) => `${item.kind}:${item.id}`,
    [],
  );
  const empty = suppressEmpty ? null : loading ? (
    <View style={styles.projectionEmpty}>
      <ActivityIndicator color="#888888" />
      <Text style={styles.projectionEmptyCopy}>Loading…</Text>
    </View>
  ) : (
    <View style={styles.projectionEmpty}>
      <Text style={styles.projectionEmptyTitle}>
        {error === null
          ? emptyTitle ?? 'Nothing to show yet'
          : 'Unable to load'}
      </Text>
      <Text style={styles.projectionEmptyCopy}>{error ?? emptyCopy}</Text>
    </View>
  );

  return (
    <FlatList
      contentContainerStyle={styles.resultList}
      data={items}
      keyExtractor={keyExtractor}
      ListEmptyComponent={empty}
      ListFooterComponent={footer ?? null}
      ListHeaderComponent={header ?? null}
      renderItem={renderItem}
    />
  );
}

function formatConversationDate(value: string | null): string {
  if (value === null) {
    return 'Time unavailable';
  }
  return new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    month: 'short',
  }).format(new Date(value));
}

function formatConversationDuration(
  startedAt: string | null,
  finishedAt: string | null,
): string {
  if (startedAt === null || finishedAt === null) {
    return 'Duration unavailable';
  }
  const duration = Date.parse(finishedAt) - Date.parse(startedAt);
  if (!Number.isFinite(duration) || duration < 0) {
    return 'Duration unavailable';
  }
  const minutes = Math.round(duration / 60_000);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes === 0
    ? `${hours} hr`
    : `${hours} hr ${remainingMinutes} min`;
}

const ConversationRow = memo(function ConversationRow({
  item,
  selected,
  onPress,
}: {
  item: ConversationProjection;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <FocusPressable
      accessibilityLabel={`Open conversation ${item.title}`}
      accessibilityRole="button"
      accessibilityState={{selected}}
      onPress={onPress}
      style={({pressed}) => [
        styles.conversationRow,
        selected && styles.conversationRowSelected,
        pressed && styles.pressed,
      ]}>
      <View style={styles.conversationRowMeta}>
        <Text style={styles.conversationRowTime}>
          {formatConversationDate(item.startedAt ?? item.createdAt)}
        </Text>
        <Text
          accessibilityLabel={
            item.starred ? 'Starred conversation' : 'Not starred'
          }
          style={styles.conversationRowStar}>
          {item.starred ? '★' : '☆'}
        </Text>
      </View>
      <Text numberOfLines={1} style={styles.resultTitle}>
        {item.title}
      </Text>
      <Text numberOfLines={2} style={styles.resultSummary}>
        {item.summary}
      </Text>
      <Text style={styles.conversationRowDuration}>
        {formatConversationDuration(item.startedAt, item.finishedAt)}
      </Text>
    </FocusPressable>
  );
});

function ConversationsPage({
  outcome,
  loading,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
  const conversations = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is ConversationProjection =>
              item.kind === 'conversation',
          )
        : [],
    [outcome],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [starredOnly, setStarredOnly] = useState(false);
  const nowEpochMilliseconds = useRef(Date.now()).current;
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return conversations.filter(
      item =>
        (!starredOnly || item.starred) &&
        (normalized === '' ||
          item.title.toLocaleLowerCase().includes(normalized) ||
          item.summary.toLocaleLowerCase().includes(normalized)),
    );
  }, [conversations, query, starredOnly]);
  useEffect(() => {
    if (selectedId !== null && !filtered.some(item => item.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);
  const grouped = useMemo(
    () =>
      filtered.reduce<Array<{label: string; items: ConversationProjection[]}>>(
        (groups, item) => {
          const label = conversationGroupLabel(
            item.startedAt ?? item.createdAt,
            nowEpochMilliseconds,
          );
          const current = groups.find(group => group.label === label);
          if (current !== undefined) {
            current.items.push(item);
          } else {
            groups.push({label, items: [item]});
          }
          return groups;
        },
        [],
      ),
    [filtered, nowEpochMilliseconds],
  );
  const filtering = query.trim() !== '' || starredOnly;

  return (
    <View style={styles.conversationPage}>
      <Text style={styles.projectionTitle}>Conversations</Text>
      <View style={styles.conversationDiscovery}>
        <View style={styles.conversationSearchBox}>
          <Search accessible={false} color="#777777" size={17} />
          <TextInput
            accessibilityLabel="Search loaded conversations"
            onChangeText={setQuery}
            placeholder="Search loaded conversations"
            placeholderTextColor="#666666"
            style={styles.memorySearchInput}
            value={query}
          />
        </View>
        <FocusPressable
          accessibilityLabel="Show starred conversations"
          accessibilityRole="button"
          accessibilityState={{selected: starredOnly}}
          onPress={() => setStarredOnly(value => !value)}
          style={({pressed}) => [
            styles.conversationStarFilter,
            starredOnly && styles.conversationStarFilterActive,
            pressed && styles.pressed,
          ]}>
          <Text
            style={[
              styles.conversationStarFilterText,
              starredOnly && styles.conversationStarFilterTextActive,
            ]}>
            Starred
          </Text>
        </FocusPressable>
      </View>
      <View style={styles.conversationContent}>
        <ScrollView
          contentContainerStyle={styles.conversationList}
          style={styles.conversationListPane}>
          {loading && outcome === null ? (
            <View style={styles.projectionEmpty}>
              <ActivityIndicator color="#888888" />
              <Text style={styles.projectionEmptyCopy}>
                Loading conversations…
              </Text>
            </View>
          ) : error !== null ? (
            <View style={styles.projectionEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                Conversations unavailable
              </Text>
              <Text style={styles.projectionEmptyCopy}>
                Conversations could not be loaded.
              </Text>
            </View>
          ) : grouped.length === 0 ? (
            <View style={styles.projectionEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                {filtering
                  ? 'No loaded conversations match.'
                  : 'No conversations yet.'}
              </Text>
              {filtering && (
                <Text style={styles.projectionEmptyCopy}>
                  Search and filters cover conversations already loaded on this
                  device.
                </Text>
              )}
            </View>
          ) : (
            grouped.map(group => (
              <View key={group.label} style={styles.conversationGroup}>
                <Text style={styles.conversationGroupTitle}>{group.label}</Text>
                {group.items.map(item => (
                  <ConversationRow
                    item={item}
                    key={item.id}
                    onPress={() => setSelectedId(item.id)}
                    selected={selectedId === item.id}
                  />
                ))}
              </View>
            ))
          )}
          {outcome?.status === 'success' && (
            <ReadStatus label="Conversations" page={outcome.value.page} />
          )}
        </ScrollView>
        <View
          accessibilityLabel="Selected conversation metadata"
          style={styles.conversationDetail}>
          {selected === null ? (
            <View style={styles.conversationDetailEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                Select a conversation
              </Text>
              <Text style={styles.projectionEmptyCopy}>
                Choose a loaded row to review its saved metadata.
              </Text>
            </View>
          ) : (
            <>
              <Text style={styles.conversationDetailEyebrow}>
                LOADED LIST METADATA
              </Text>
              <Text style={styles.conversationDetailTitle}>
                {selected.title}
              </Text>
              <Text style={styles.conversationDetailSummary}>
                {selected.summary}
              </Text>
              <View style={styles.conversationDetailFields}>
                <Text style={styles.conversationDetailField}>
                  Started · {formatConversationDate(selected.startedAt)}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Finished · {formatConversationDate(selected.finishedAt)}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Duration ·{' '}
                  {formatConversationDuration(
                    selected.startedAt,
                    selected.finishedAt,
                  )}
                </Text>
                <Text style={styles.conversationDetailField}>
                  Status · {selected.status}
                </Text>
                <Text style={styles.conversationDetailField}>
                  {selected.locked ? 'Locked record' : 'Unlocked record'}
                </Text>
                <Text style={styles.conversationDetailField}>
                  {selected.discarded ? 'Discarded record' : 'Active record'}
                </Text>
              </View>
              <Text style={styles.conversationDetailNotice}>
                No fetched conversation detail, transcript, playback, folders,
                or actions are shown here.
              </Text>
            </>
          )}
        </View>
      </View>
    </View>
  );
}

function formatMemoryDate(timestamp: number | null): string {
  if (timestamp === null) {
    return 'Date unavailable';
  }
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function MemoriesPage({
  outcome,
  loading,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
  const loaded = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is MemoryProjection => item.kind === 'memory',
          )
        : [],
    [outcome],
  );
  const [items, setItems] = useState<MemoryProjection[]>(loaded);
  const [page, setPage] = useState<ReadPageState | null>(
    outcome?.status === 'success' ? outcome.value.page : null,
  );
  const [query, setQuery] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  useEffect(() => {
    if (outcome?.status === 'success') {
      setItems(loaded);
      setPage(outcome.value.page);
      setLoadMoreError(false);
    }
  }, [loaded, outcome]);
  const results = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized === ''
      ? items
      : items.filter(item =>
          item.searchableText.toLocaleLowerCase().includes(normalized),
        );
  }, [items, query]);
  const loadMore = async () => {
    if (
      omiBackend === null ||
      omiBackend === undefined ||
      page?.nextCursor === null ||
      page?.nextCursor === undefined ||
      loadingMore
    ) {
      return;
    }
    setLoadingMore(true);
    setLoadMoreError(false);
    try {
      const next = await loadMemories(omiBackend, page.nextCursor);
      setItems(current => {
        const ids = new Set(current.map(item => item.id));
        return [...current, ...next.items.filter(item => !ids.has(item.id))];
      });
      setPage(next.page);
    } catch {
      setLoadMoreError(true);
    } finally {
      setLoadingMore(false);
    }
  };
  const renderItem = useCallback(
    ({item}: {item: MemoryProjection}) => (
      <View
        accessibilityLabel={`Memory: ${item.title}`}
        style={styles.memoryCard}>
        <View style={styles.memoryMetaRow}>
          <Text style={styles.memoryTimestamp}>
            {formatMemoryDate(item.timestamp)}
          </Text>
          <Text style={styles.memoryCitationCount}>
            {item.citations.length === 1
              ? '1 citation'
              : `${item.citations.length} citations`}
          </Text>
        </View>
        <Text style={styles.memoryBody}>{item.summary}</Text>
        <Text style={styles.memoryProvenance}>Synthesized memory</Text>
      </View>
    ),
    [],
  );
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = query.trim() !== '';
  return (
    <View style={styles.memoryPage}>
      <Text style={styles.projectionTitle}>Memories</Text>
      <View style={styles.memorySearchBox}>
        <Search accessible={false} color="#777777" size={17} />
        <TextInput
          accessibilityLabel="Search loaded memories"
          onChangeText={setQuery}
          placeholder="Search loaded memories"
          placeholderTextColor="#666666"
          style={styles.memorySearchInput}
          value={query}
        />
      </View>
      {loading && outcome === null ? (
        <View style={styles.projectionEmpty}>
          <ActivityIndicator color="#888888" />
          <Text style={styles.projectionEmptyCopy}>Loading memories…</Text>
        </View>
      ) : error !== null ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>Memories unavailable</Text>
          <Text style={styles.projectionEmptyCopy}>{error}</Text>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.memoryList}
          data={results}
          keyExtractor={item => item.id}
          ListEmptyComponent={
            <View style={styles.projectionEmpty}>
              <Text style={styles.projectionEmptyTitle}>
                {filtering ? 'No loaded memories match.' : 'No memories yet.'}
              </Text>
              {filtering && (
                <Text style={styles.projectionEmptyCopy}>
                  Search covers the memories loaded on this device.
                </Text>
              )}
            </View>
          }
          ListFooterComponent={
            page === null ? null : (
              <View style={styles.memoryFooter}>
                <ReadStatus label="Memories" page={page} />
                {page.hasMore && page.nextCursor !== null && (
                  <FocusPressable
                    accessibilityLabel="Load more memories"
                    accessibilityRole="button"
                    disabled={loadingMore}
                    onPress={loadMore}
                    style={({pressed}) => [
                      styles.loadOlderButton,
                      pressed && styles.pressed,
                    ]}>
                    <Text style={styles.loadOlderText}>
                      {loadingMore ? 'Loading more…' : 'Load more'}
                    </Text>
                  </FocusPressable>
                )}
                {loadMoreError && (
                  <Text style={styles.error}>
                    More memories could not be loaded.
                  </Text>
                )}
              </View>
            )
          }
          renderItem={renderItem}
        />
      )}
    </View>
  );
}

const taskGroups: TaskGroup[] = ['Today', 'Tomorrow', 'Later'];

function formatTaskDue(dueAt: number | null): string {
  if (dueAt === null) {
    return 'No due date';
  }
  return new Date(dueAt * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

function TasksPage({
  outcome,
  loading,
}: {
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const nowEpochSeconds = useRef(Math.floor(Date.now() / 1000)).current;
  const tasks = useMemo(
    () =>
      outcome?.status === 'success'
        ? outcome.value.items.filter(
            (item): item is TaskProjection => item.kind === 'task',
          )
        : [],
    [outcome],
  );
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized === ''
      ? tasks
      : tasks.filter(task =>
          task.title.toLocaleLowerCase().includes(normalized),
        );
  }, [query, tasks]);
  const grouped = useMemo(
    () =>
      taskGroups.map(label => ({
        label,
        tasks: filtered.filter(
          task => taskGroup(task.dueAt, nowEpochSeconds) === label,
        ),
      })),
    [filtered, nowEpochSeconds],
  );
  const error = outcome?.status === 'error' ? outcome.error : null;
  const filtering = query.trim() !== '';
  return (
    <View style={styles.tasksPage}>
      <Text style={styles.projectionTitle}>Tasks</Text>
      <View style={styles.taskSearchBox}>
        <Search accessible={false} color="#777777" size={17} />
        <TextInput
          accessibilityLabel="Search loaded tasks"
          onChangeText={setQuery}
          placeholder="Search loaded tasks"
          placeholderTextColor="#666666"
          style={styles.memorySearchInput}
          value={query}
        />
      </View>
      {loading && outcome === null ? (
        <View style={styles.projectionEmpty}>
          <ActivityIndicator color="#888888" />
          <Text style={styles.projectionEmptyCopy}>Loading tasks…</Text>
        </View>
      ) : error !== null ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>Tasks unavailable</Text>
          <Text style={styles.projectionEmptyCopy}>
            Saved tasks could not be loaded.
          </Text>
        </View>
      ) : filtered.length === 0 ? (
        <View style={styles.projectionEmpty}>
          <Text style={styles.projectionEmptyTitle}>
            {filtering ? 'No loaded tasks match.' : 'No tasks yet.'}
          </Text>
          {filtering && (
            <Text style={styles.projectionEmptyCopy}>
              Search covers task descriptions already loaded on this device.
            </Text>
          )}
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.taskList}>
          {grouped.map(group =>
            group.tasks.length === 0 ? null : (
              <View key={group.label} style={styles.taskGroup}>
                <View style={styles.taskGroupHeader}>
                  <Text style={styles.taskGroupTitle}>{group.label}</Text>
                  <Text style={styles.taskGroupCount}>
                    {group.tasks.length}
                  </Text>
                </View>
                {group.tasks.map(task => {
                  const selected = task.id === selectedId;
                  return (
                    <FocusPressable
                      accessibilityLabel={`${
                        task.completed ? 'Completed' : 'Open'
                      } task: ${task.title}`}
                      accessibilityRole="button"
                      accessibilityState={{selected}}
                      key={task.id}
                      onPress={() => setSelectedId(task.id)}
                      style={({pressed}) => [
                        styles.taskCard,
                        selected && styles.taskCardSelected,
                        pressed && styles.pressed,
                      ]}>
                      <View
                        accessibilityElementsHidden
                        importantForAccessibility="no-hide-descendants"
                        style={[
                          styles.taskCompletion,
                          task.completed && styles.taskCompletionDone,
                        ]}>
                        {task.completed && (
                          <Text style={styles.taskCheck}>✓</Text>
                        )}
                      </View>
                      <View style={styles.taskCardText}>
                        <Text
                          style={[
                            styles.taskDescription,
                            task.completed && styles.taskDescriptionDone,
                          ]}>
                          {task.title}
                        </Text>
                        <Text style={styles.taskDue}>
                          {task.completed
                            ? `Completed · ${formatTaskDue(task.dueAt)}`
                            : formatTaskDue(task.dueAt)}
                        </Text>
                      </View>
                    </FocusPressable>
                  );
                })}
              </View>
            ),
          )}
          {outcome?.status === 'success' && (
            <ReadStatus label="Tasks" page={outcome.value.page} />
          )}
        </ScrollView>
      )}
      <View
        accessibilityLabel="Task keyboard shortcuts"
        style={styles.taskShortcuts}>
        <Text style={styles.taskShortcut}>Tab · Focus</Text>
        <Text style={styles.taskShortcut}>Enter · Select</Text>
      </View>
    </View>
  );
}

function ReadStatus({label, page}: {label: string; page: ReadPageState}) {
  if (page.complete && page.completenessStatus === 'complete') {
    return null;
  }
  const detail = page.hasMore
    ? page.nextCursor === null
      ? `Showing the first 50 ${label.toLowerCase()}. More may be available.`
      : `More ${label.toLowerCase()} are available.`
    : page.completenessStatus === 'degraded'
    ? `${label} may be temporarily incomplete.`
    : `${label} are incomplete.`;
  return (
    <View style={styles.readStatus}>
      <Text style={styles.readStatusText}>{detail}</Text>
    </View>
  );
}

function OutcomeStatus({
  label,
  outcome,
}: {
  label: string;
  outcome: DomainReadOutcome<DesktopReadProjection>;
}) {
  return outcome.status === 'error' ? (
    <View style={styles.readStatus}>
      <Text style={styles.readStatusText}>{label} are unavailable.</Text>
    </View>
  ) : (
    <ReadStatus label={label} page={outcome.value.page} />
  );
}

function formatChatTime(createdAt: number): string {
  const milliseconds =
    createdAt > 100_000_000_000 ? createdAt : createdAt * 1000;
  return new Date(milliseconds).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

const ChatMessageRow = memo(function ChatMessageRow({
  animate,
  compact,
  message,
  reduceMotion,
}: {
  animate: boolean;
  compact: boolean;
  message: ChatMessage;
  reduceMotion: boolean;
}) {
  const opacity = useRef(new Animated.Value(animate ? 0 : 1)).current;
  const translateY = useRef(
    new Animated.Value(animate && !reduceMotion ? 10 : 0),
  ).current;
  useEffect(() => {
    if (!animate) {
      return;
    }
    Animated.parallel([
      Animated.timing(opacity, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [animate, opacity, reduceMotion, translateY]);
  const human = message.sender === 'human';
  return (
    <Animated.View
      accessibilityLabel={
        message.generationOutcome === 'failed' ? 'Failed response' : undefined
      }
      style={[
        styles.chatMessageRow,
        human ? styles.chatMessageRowHuman : styles.chatMessageRowAi,
        {opacity, transform: [{translateY}]},
      ]}>
      {!human && <OmiAvatar />}
      <View
        style={[
          styles.chatMessageColumn,
          compact
            ? styles.chatMessageColumnCompact
            : styles.chatMessageColumnDesktop,
          human && styles.chatMessageColumnHuman,
        ]}>
        <View
          style={[
            styles.chatBubble,
            human ? styles.chatBubbleHuman : styles.chatBubbleAi,
            message.generationOutcome === 'cancelled' &&
              styles.cancelledMessage,
          ]}>
          {message.generationOutcome === 'failed' ? (
            <Text style={styles.failedLabel}>
              {message.generationRetryable === true
                ? 'Response failed. Try again.'
                : 'Response failed.'}
            </Text>
          ) : (
            <Text style={styles.message}>{message.text}</Text>
          )}
        </View>
        {message.generationOutcome === 'cancelled' && (
          <Text style={styles.cancelledLabel}>Response stopped</Text>
        )}
        <Text
          style={[styles.chatTimestamp, human && styles.chatTimestampHuman]}>
          {formatChatTime(message.createdAt)}
        </Text>
      </View>
    </Animated.View>
  );
});

function ChatThinking({reduceMotion}: {reduceMotion: boolean}) {
  const dots = useRef([
    new Animated.Value(1),
    new Animated.Value(1),
    new Animated.Value(1),
  ]).current;
  useEffect(() => {
    if (reduceMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.stagger(
        150,
        dots.map(dot =>
          Animated.sequence([
            Animated.timing(dot, {
              duration: 300,
              toValue: 0.3,
              useNativeDriver: true,
            }),
            Animated.timing(dot, {
              duration: 300,
              toValue: 1,
              useNativeDriver: true,
            }),
          ]),
        ),
      ),
    );
    animation.start();
    return () => animation.stop();
  }, [dots, reduceMotion]);
  return (
    <View style={[styles.chatMessageRow, styles.chatMessageRowAi]}>
      <OmiAvatar />
      <View
        accessibilityLabel="Thinking"
        style={[styles.chatBubble, styles.chatBubbleAi]}>
        {reduceMotion ? (
          <Text style={styles.thinkingText}>Thinking…</Text>
        ) : (
          <View style={styles.thinkingDots}>
            {dots.map((opacity, index) => (
              <Animated.View
                key={index}
                style={[styles.thinkingDot, {opacity}]}
              />
            ))}
          </View>
        )}
      </View>
    </View>
  );
}

function App(): React.JSX.Element {
  const {width} = useWindowDimensions();
  const macDesktop = Platform.OS === 'macos';
  const compact = width < 1024;
  const floatingPane = width >= 640;
  const composerMaxWidth = width >= 1280 ? 820 : width >= 768 ? 720 : 640;
  const stageOpacity = useRef(new Animated.Value(0)).current;
  const stageTranslateY = useRef(new Animated.Value(8)).current;
  const restingOpacity = useRef(new Animated.Value(0)).current;
  const restingTranslateY = useRef(new Animated.Value(8)).current;
  const mobileNavOpacity = useRef(new Animated.Value(0)).current;
  const mobileNavTranslateY = useRef(new Animated.Value(100)).current;
  const activePillTranslateY = useRef(new Animated.Value(0)).current;
  const railWidth = useRef(new Animated.Value(72)).current;
  const [reduceMotion, setReduceMotion] = useState(false);
  const [railExpanded, setRailExpanded] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const stableChatMessageIds = useRef(new Set<string>()).current;
  const animatedChatMessageIds = useRef(new Set<string>()).current;
  const chatScrollRef = useRef<ScrollView>(null);
  const shouldFollowChat = useRef(false);
  const [olderChatCursor, setOlderChatCursor] = useState<string | null>(null);
  const [hasOlderChat, setHasOlderChat] = useState(false);
  const [loadingOlderChat, setLoadingOlderChat] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(
    null,
  );
  const [chatError, setChatError] = useState<string | null>(null);
  const [route, setRoute] = useState<Route>('Home');
  const [readOutcomes, setReadOutcomes] = useState<DesktopReadOutcomes | null>(
    null,
  );
  const readOutcomesRef = useRef<DesktopReadOutcomes | null>(null);
  const [readsPhase, setReadsPhase] = useState<ReadsPhase>('initial-loading');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [composerFocused, setComposerFocused] = useState(false);
  const [projectionFilter, setProjectionFilter] =
    useState<ProjectionFilter>('all');
  const searchRef = useRef<TextInput>(null);
  const activeNavigationIndex = navigation.findIndex(
    item => route === item.label,
  );

  useEffect(() => {
    let active = true;
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      return () => undefined;
    }
    loadNewestChatHistory(backend)
      .then(page => {
        if (active) {
          page.messages.forEach(message =>
            stableChatMessageIds.add(message.id),
          );
          setMessages(page.messages);
          setOlderChatCursor(page.olderCursor);
          setHasOlderChat(page.hasOlder);
        }
      })
      .catch(() => {
        if (active) {
          setChatError('Chat is temporarily unavailable.');
        }
      });
    return () => {
      active = false;
    };
  }, [stableChatMessageIds]);

  useEffect(() => {
    if (route === 'Chat' && shouldFollowChat.current) {
      chatScrollRef.current?.scrollToEnd({animated: !reduceMotion});
    }
  }, [chatBusy, messages, reduceMotion, route]);

  const refreshReads = useCallback(async (initial: boolean) => {
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      const unavailable = {
        status: 'error',
        error: 'Backend unavailable',
      } as const;
      setReadOutcomes({
        conversations: unavailable,
        memories: unavailable,
        tasks: unavailable,
      });
      setReadsPhase('unavailable');
      return;
    }
    setReadsPhase(
      initial && readOutcomesRef.current === null
        ? 'initial-loading'
        : 'refreshing',
    );
    try {
      const outcomes = await loadDesktopReads(backend);
      const previous = readOutcomesRef.current;
      const hadSavedRows =
        previous !== null &&
        [previous.conversations, previous.memories].some(
          outcome =>
            outcome.status === 'success' && outcome.value.items.length > 0,
        );
      const homeOutcomes = [outcomes.conversations, outcomes.memories];
      const failed = homeOutcomes.some(outcome => outcome.status === 'error');
      setReadOutcomes(current => {
        let next: DesktopReadOutcomes;
        if (current === null) {
          next = outcomes;
        } else {
          next = {
            conversations:
              outcomes.conversations.status === 'success'
                ? outcomes.conversations
                : current.conversations,
            memories:
              outcomes.memories.status === 'success'
                ? outcomes.memories
                : current.memories,
            tasks:
              outcomes.tasks.status === 'success'
                ? outcomes.tasks
                : current.tasks,
          };
        }
        readOutcomesRef.current = next;
        return next;
      });
      const hasSavedRows = homeOutcomes.some(
        outcome =>
          outcome.status === 'success' && outcome.value.items.length > 0,
      );
      setReadsPhase(
        failed
          ? hasSavedRows || hadSavedRows
            ? 'saved-but-refresh-failed'
            : 'unavailable'
          : 'ready',
      );
    } catch {
      setReadsPhase(
        readOutcomesRef.current === null
          ? 'unavailable'
          : 'saved-but-refresh-failed',
      );
    }
  }, []);

  useEffect(() => {
    refreshReads(true).catch(() => undefined);
  }, [refreshReads]);

  const reads = useMemo(() => {
    if (readOutcomes === null) {
      return [];
    }
    return [
      ...(readOutcomes.conversations.status === 'success'
        ? readOutcomes.conversations.value.items
        : []),
      ...(readOutcomes.memories.status === 'success'
        ? readOutcomes.memories.value.items
        : []),
    ].sort((left, right) => {
      const timestamp = (item: DesktopReadProjection) =>
        item.kind === 'conversation'
          ? Date.parse(item.startedAt ?? item.createdAt)
          : item.kind === 'memory'
          ? item.timestamp ?? 0
          : 0;
      return timestamp(right) - timestamp(left);
    });
  }, [readOutcomes]);

  const routeOutcome = useMemo(() => {
    if (readOutcomes === null || route === 'Home' || route === 'Chat') {
      return null;
    }
    return {
      Conversations: readOutcomes.conversations,
      Memories: readOutcomes.memories,
      Tasks: readOutcomes.tasks,
    }[route] as DomainReadOutcome<DesktopReadProjection>;
  }, [readOutcomes, route]);

  const homeResults = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return reads.filter(
      item =>
        (projectionFilter === 'all' || item.kind === projectionFilter) &&
        (query === '' ||
          item.searchableText.toLocaleLowerCase().includes(query)),
    );
  }, [projectionFilter, reads, searchQuery]);
  const homeFiltering = searchQuery.trim() !== '' || projectionFilter !== 'all';

  useEffect(() => {
    if (route === 'Home') {
      searchRef.current?.focus();
    }
  }, [route]);

  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setRoute('Home');
      searchRef.current?.focus();
    });
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().then(enabled => {
      if (active) {
        setReduceMotion(enabled);
      }
    });
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotion,
    );
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    stageOpacity.setValue(0);
    stageTranslateY.setValue(reduceMotion ? 0 : 8);
    Animated.parallel([
      Animated.timing(stageOpacity, {
        duration: reduceMotion ? 1 : 180,
        easing: Easing.bezier(0.22, 1, 0.36, 1),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(stageTranslateY, {
        duration: reduceMotion ? 1 : 180,
        easing: Easing.bezier(0.22, 1, 0.36, 1),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [reduceMotion, route, stageOpacity, stageTranslateY]);

  useEffect(() => {
    if (route !== 'Chat' || messages.length !== 0 || chatBusy) {
      return;
    }
    restingOpacity.setValue(0);
    restingTranslateY.setValue(reduceMotion ? 0 : 8);
    Animated.parallel([
      Animated.timing(restingOpacity, {
        duration: reduceMotion ? 1 : 250,
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(restingTranslateY, {
        duration: reduceMotion ? 1 : 250,
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [
    chatBusy,
    messages.length,
    reduceMotion,
    restingOpacity,
    restingTranslateY,
    route,
  ]);

  useEffect(() => {
    if (!compact) {
      mobileNavOpacity.setValue(1);
      mobileNavTranslateY.setValue(0);
      return;
    }
    mobileNavOpacity.setValue(0);
    mobileNavTranslateY.setValue(reduceMotion ? 0 : 100);
    Animated.parallel([
      Animated.timing(mobileNavOpacity, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(mobileNavTranslateY, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [compact, mobileNavOpacity, mobileNavTranslateY, reduceMotion]);

  useEffect(() => {
    const value = Math.max(activeNavigationIndex, 0) * 52;
    if (reduceMotion) {
      activePillTranslateY.setValue(value);
      return;
    }
    Animated.spring(activePillTranslateY, {
      damping: 42,
      stiffness: 520,
      toValue: value,
      useNativeDriver: true,
    }).start();
  }, [activeNavigationIndex, activePillTranslateY, reduceMotion]);

  useEffect(() => {
    const value = railExpanded ? 280 : 72;
    if (reduceMotion) {
      railWidth.setValue(value);
      return;
    }
    Animated.timing(railWidth, {
      duration: 200,
      easing: Easing.bezier(0.42, 0, 0.58, 1),
      toValue: value,
      useNativeDriver: false,
    }).start();
  }, [railExpanded, railWidth, reduceMotion]);

  const nav = (
    <Animated.View
      accessibilityRole="tablist"
      style={[
        styles.navigation,
        compact ? styles.bottomNav : styles.rail,
        !compact && {width: railWidth},
        compact && {
          opacity: mobileNavOpacity,
          transform: [{translateY: mobileNavTranslateY}],
        },
      ]}>
      {!compact && (
        <View
          style={[
            styles.railHeader,
            railExpanded && styles.railHeaderExpanded,
          ]}>
          <Text style={styles.wordmark}>omi</Text>
          <FocusPressable
            accessibilityLabel={
              railExpanded ? 'Collapse sidebar' : 'Expand sidebar'
            }
            accessibilityRole="button"
            onPress={() => setRailExpanded(current => !current)}
            style={({pressed}) => [
              styles.railToggle,
              pressed && styles.pressed,
            ]}>
            {railExpanded ? (
              <PanelLeftClose color="#888888" size={20} strokeWidth={2} />
            ) : (
              <PanelLeft color="#888888" size={20} strokeWidth={2} />
            )}
          </FocusPressable>
        </View>
      )}
      <View style={[styles.navItems, compact && styles.navItemsCompact]}>
        {!compact && (
          <Animated.View
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            style={[
              styles.activePill,
              activeNavigationIndex < 0 && styles.activePillHidden,
              {
                transform: [{translateY: activePillTranslateY}],
              },
            ]}
          />
        )}
        {navigation.map(item => (
          <NavItem
            active={route === item.label}
            compact={compact}
            icon={item.icon}
            key={item.label}
            expanded={railExpanded}
            label={item.label}
            onPress={() => setRoute(item.label as Route)}
          />
        ))}
      </View>
    </Animated.View>
  );

  const macDesktopNav = (
    <View style={styles.macTopNavFrame}>
      <OmiGlassPanel
        accessibilityLabel="Desktop navigation material"
        pointerEvents="none"
        style={styles.macGlassPanel}
      />
      <View
        accessibilityLabel="Desktop navigation"
        accessibilityRole="tablist"
        style={styles.macTopNav}>
        {navigation.map(item => {
          const Icon = item.icon;
          const active = route === item.label;
          return (
            <FocusPressable
              accessibilityLabel={`${item.label} navigation`}
              accessibilityRole="tab"
              accessibilityState={{selected: active}}
              key={item.label}
              onPress={() => setRoute(item.label as Route)}
              style={({pressed}) => [
                styles.macTopNavItem,
                active && styles.macTopNavItemActive,
                pressed && styles.pressed,
              ]}>
              <Icon
                accessible={false}
                color={active ? '#141414' : '#505050'}
                size={18}
                strokeWidth={2}
              />
              <Text
                style={[
                  styles.macTopNavText,
                  active && styles.macTopNavTextActive,
                ]}>
                {item.label}
              </Text>
            </FocusPressable>
          );
        })}
      </View>
    </View>
  );

  const send = async () => {
    const text = draft.trim();
    const backend = omiBackend;
    if (backend === undefined || backend === null || text === '' || chatBusy) {
      return;
    }
    setChatBusy(true);
    setChatError(null);
    shouldFollowChat.current = true;
    const localMessage = createLocalChatMessage(text);
    setMessages(current => [...current, localMessage]);
    setDraft('');
    try {
      const result = await sendChatMessage(
        backend,
        text,
        localMessage.createdAt,
        id => {
          setActiveGenerationId(id);
        },
        localMessage,
      );
      setMessages(current => {
        const echoIndex = current.findIndex(
          message => message.id === localMessage.id,
        );
        const withoutCanonical = current.filter(
          message =>
            message.id !== result.human.id &&
            message.id !== result.assistant?.id,
        );
        if (echoIndex < 0) {
          return [
            ...withoutCanonical,
            result.human,
            ...(result.assistant === null ? [] : [result.assistant]),
          ];
        }
        const insertAt = Math.min(echoIndex, withoutCanonical.length);
        return [
          ...withoutCanonical.slice(0, insertAt),
          result.human,
          ...(result.assistant === null ? [] : [result.assistant]),
          ...withoutCanonical.slice(insertAt),
        ];
      });
    } catch (error) {
      setChatError(chatErrorCopy(error));
    } finally {
      setActiveGenerationId(null);
      setChatBusy(false);
    }
  };

  const loadOlderMessages = async () => {
    const backend = omiBackend;
    const cursor = olderChatCursor;
    if (
      backend === undefined ||
      backend === null ||
      cursor === null ||
      loadingOlderChat
    ) {
      return;
    }
    setLoadingOlderChat(true);
    setChatError(null);
    try {
      const page = await loadOlderChatHistory(backend, cursor);
      page.messages.forEach(message => stableChatMessageIds.add(message.id));
      setMessages(current => mergeOlderChatHistory(current, page.messages));
      setOlderChatCursor(page.olderCursor);
      setHasOlderChat(page.hasOlder);
    } catch (error) {
      if (
        error instanceof ChatBackendError &&
        error.status === 410 &&
        error.action === 'refresh_history'
      ) {
        try {
          const page = await loadNewestChatHistory(backend);
          page.messages.forEach(message =>
            stableChatMessageIds.add(message.id),
          );
          setMessages(current =>
            reconcileCanonicalChatHistory(
              current.filter(message => message.localOnly === true),
              page.messages,
            ),
          );
          setOlderChatCursor(page.olderCursor);
          setHasOlderChat(page.hasOlder);
          return;
        } catch {}
      }
      setChatError('Older messages could not be loaded.');
    } finally {
      setLoadingOlderChat(false);
    }
  };

  const stopGeneration = async () => {
    const backend = omiBackend;
    const generationId = activeGenerationId;
    if (backend === undefined || backend === null || generationId === null) {
      return;
    }
    try {
      await cancelChatGeneration(backend, generationId);
    } catch {
      setChatError('Could not stop the response.');
    }
  };

  const shouldAnimateChatMessage = (id: string) => {
    if (stableChatMessageIds.has(id) || animatedChatMessageIds.has(id)) {
      return false;
    }
    animatedChatMessageIds.add(id);
    return true;
  };

  const composer = (
    <View style={[styles.composerWrap, compact && styles.composerWrapCompact]}>
      <View
        style={[
          styles.composer,
          composerFocused && styles.composerFocused,
          {maxWidth: composerMaxWidth},
        ]}>
        <TextInput
          accessibilityLabel="Ask Omi"
          multiline
          onBlur={() => setComposerFocused(false)}
          onChangeText={setDraft}
          onFocus={() => setComposerFocused(true)}
          placeholder="Ask anything..."
          placeholderTextColor="#888888"
          style={styles.composerInput}
          value={draft}
        />
        <View style={styles.composerActions}>
          <FocusPressable
            accessibilityLabel="Attach file unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Paperclip color="#666666" size={18} strokeWidth={2} />
          </FocusPressable>
          <FocusPressable
            accessibilityLabel="Dictation unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Mic color="#666666" size={18} strokeWidth={2} />
          </FocusPressable>
          <View style={styles.actionSpacer} />
          <FocusPressable
            accessibilityLabel={
              activeGenerationId !== null
                ? 'Stop response'
                : omiBackend === undefined || omiBackend === null
                ? 'Send message unavailable'
                : 'Send message'
            }
            accessibilityRole="button"
            disabled={
              omiBackend === undefined ||
              omiBackend === null ||
              (activeGenerationId === null && (draft.trim() === '' || chatBusy))
            }
            onPress={activeGenerationId === null ? send : stopGeneration}
            style={({pressed}) => [
              styles.sendButton,
              draft.trim() !== '' &&
                !chatBusy &&
                omiBackend !== undefined &&
                omiBackend !== null &&
                styles.sendButtonEnabled,
              activeGenerationId !== null && styles.stopButton,
              pressed && styles.pressed,
            ]}>
            {activeGenerationId === null ? (
              <ArrowUp color="#141414" size={18} strokeWidth={2.5} />
            ) : (
              <Square
                color="#141414"
                fill="#141414"
                size={13}
                strokeWidth={2}
              />
            )}
          </FocusPressable>
        </View>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={[styles.outer, macDesktop && styles.macOuter]}>
      <View
        style={[
          styles.shell,
          !compact && !macDesktop && styles.shellWide,
          macDesktop && styles.macShell,
        ]}>
        {macDesktop ? macDesktopNav : !compact ? nav : null}
        <View
          style={[
            styles.paneInset,
            !floatingPane && styles.paneInsetCompact,
            macDesktop && styles.macPaneInset,
          ]}>
          <View
            accessibilityLabel="Floating pane"
            style={[
              styles.paneFrame,
              !floatingPane && styles.paneFrameCompact,
            ]}>
            {floatingPane && !macDesktop && (
              <View
                accessibilityLabel="Floating pane depth"
                pointerEvents="none"
                style={styles.paneDepth}>
                <View style={[styles.paneDepthLayer, styles.paneDepthWide]} />
                <View style={[styles.paneDepthLayer, styles.paneDepthMid]} />
                <View style={[styles.paneDepthLayer, styles.paneDepthNear]} />
              </View>
            )}
            <KeyboardAvoidingView
              behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
              style={[
                styles.pane,
                !floatingPane && styles.paneCompact,
                macDesktop && styles.macPane,
              ]}>
              {macDesktop && (
                <OmiGlassPanel
                  accessibilityLabel="Desktop material panel"
                  pointerEvents="none"
                  style={styles.macGlassPanel}
                />
              )}
              <Animated.View
                accessibilityLabel={`${route} stage`}
                style={[
                  styles.stageMotion,
                  {
                    opacity: stageOpacity,
                    transform: [{translateY: stageTranslateY}],
                  },
                ]}>
                <View style={[styles.stage, compact && styles.stageCompact]}>
                  {route === 'Home' ? (
                    <View style={styles.searchHome}>
                      <ProjectionList
                        emptyCopy={
                          homeFiltering
                            ? 'Clear the search or filters to see saved items.'
                            : 'Start typing to search what is saved.'
                        }
                        emptyTitle={
                          homeFiltering ? 'No results' : 'Nothing saved yet'
                        }
                        error={null}
                        footer={
                          <View style={styles.readStatuses}>
                            {readsPhase !== 'ready' && (
                              <View style={styles.readStatus}>
                                <Text style={styles.readStatusText}>
                                  {readsPhase === 'initial-loading'
                                    ? 'Loading saved data…'
                                    : readsPhase === 'refreshing'
                                    ? 'Refreshing saved data…'
                                    : readsPhase === 'saved-but-refresh-failed'
                                    ? 'Showing saved data. Could not refresh.'
                                    : 'Saved data is unavailable.'}
                                </Text>
                                {(readsPhase === 'saved-but-refresh-failed' ||
                                  readsPhase === 'unavailable') && (
                                  <FocusPressable
                                    accessibilityLabel="Retry saved data"
                                    accessibilityRole="button"
                                    onPress={() => refreshReads(false)}
                                    style={({pressed}) => [
                                      styles.retryButton,
                                      pressed && styles.pressed,
                                    ]}>
                                    <Text style={styles.retryButtonText}>
                                      Retry
                                    </Text>
                                  </FocusPressable>
                                )}
                              </View>
                            )}
                            {readOutcomes !== null && (
                              <View style={styles.readStatuses}>
                                <OutcomeStatus
                                  label="Conversations"
                                  outcome={readOutcomes.conversations}
                                />
                                <OutcomeStatus
                                  label="Memories"
                                  outcome={readOutcomes.memories}
                                />
                              </View>
                            )}
                          </View>
                        }
                        header={
                          <View style={styles.searchHeader}>
                            <Text style={styles.searchEyebrow}>HOME</Text>
                            <Text style={styles.searchTitle}>
                              Search what you’ve seen and heard
                            </Text>
                            <View
                              style={[
                                styles.searchBox,
                                searchFocused && styles.focusRing,
                              ]}>
                              <Search
                                accessible={false}
                                color="#888888"
                                size={18}
                                strokeWidth={2}
                              />
                              <TextInput
                                accessibilityLabel="Search Home"
                                autoFocus
                                onBlur={() => setSearchFocused(false)}
                                onChangeText={setSearchQuery}
                                onFocus={() => setSearchFocused(true)}
                                placeholder="Search conversations and memories"
                                placeholderTextColor="#777777"
                                ref={searchRef}
                                style={styles.searchInput}
                                value={searchQuery}
                              />
                              {searchQuery !== '' && (
                                <FocusPressable
                                  accessibilityLabel="Clear search"
                                  accessibilityRole="button"
                                  onPress={() => {
                                    setSearchQuery('');
                                    searchRef.current?.focus();
                                  }}
                                  style={({pressed}) => [
                                    styles.clearSearch,
                                    pressed && styles.pressed,
                                  ]}>
                                  <Text style={styles.clearSearchText}>×</Text>
                                </FocusPressable>
                              )}
                            </View>
                            <View style={styles.searchActions}>
                              <View style={styles.filters}>
                                {filterLabels.map(filter => (
                                  <FocusPressable
                                    accessibilityRole="button"
                                    key={filter.value}
                                    onPress={() =>
                                      setProjectionFilter(filter.value)
                                    }
                                    style={[
                                      styles.filterChip,
                                      projectionFilter === filter.value &&
                                        styles.filterChipActive,
                                    ]}>
                                    <Text
                                      style={[
                                        styles.filterText,
                                        projectionFilter === filter.value &&
                                          styles.filterTextActive,
                                      ]}>
                                      {filter.label}
                                    </Text>
                                  </FocusPressable>
                                ))}
                              </View>
                              <FocusPressable
                                accessibilityLabel="Open Chat"
                                accessibilityRole="button"
                                onPress={() => setRoute('Chat')}
                                style={({pressed}) => [
                                  styles.chatPill,
                                  pressed && styles.pressed,
                                ]}>
                                <MessageCircle
                                  color="#141414"
                                  size={17}
                                  strokeWidth={2}
                                />
                                <Text style={styles.chatPillText}>Chat</Text>
                              </FocusPressable>
                            </View>
                            <Text style={styles.timelineLabel}>LATEST</Text>
                          </View>
                        }
                        items={homeResults}
                        loading={readsPhase === 'initial-loading'}
                        suppressEmpty={readsPhase !== 'ready'}
                      />
                    </View>
                  ) : route === 'Chat' ? (
                    <ScrollView
                      accessibilityLabel="Chat scroll region"
                      contentContainerStyle={styles.chatScrollContent}
                      onScroll={(
                        event: NativeSyntheticEvent<NativeScrollEvent>,
                      ) => {
                        const {contentOffset, contentSize, layoutMeasurement} =
                          event.nativeEvent;
                        shouldFollowChat.current =
                          contentOffset.y + layoutMeasurement.height >=
                          contentSize.height - 40;
                      }}
                      ref={chatScrollRef}
                      scrollEventThrottle={16}
                      style={styles.chatScroll}>
                      <View
                        style={
                          compact
                            ? [
                                messages.length === 0 && !chatBusy
                                  ? styles.home
                                  : styles.chatHistory,
                                messages.length === 0 && !chatBusy
                                  ? styles.homeCompact
                                  : styles.chatHistoryCompact,
                              ]
                            : messages.length === 0 && !chatBusy
                            ? styles.home
                            : styles.chatHistory
                        }>
                        <FocusPressable
                          accessibilityLabel="Back to Home"
                          accessibilityRole="button"
                          onPress={() => setRoute('Home')}
                          style={({pressed}) => [
                            styles.backButton,
                            pressed && styles.pressed,
                          ]}>
                          <ChevronLeft
                            color="#b0b0b0"
                            size={18}
                            strokeWidth={2}
                          />
                          <Text style={styles.backButtonText}>Home</Text>
                        </FocusPressable>
                        {messages.length === 0 && !chatBusy ? (
                          <Animated.View
                            accessibilityLabel="Chat resting stage"
                            style={[
                              styles.restingStage,
                              {
                                opacity: restingOpacity,
                                transform: [{translateY: restingTranslateY}],
                              },
                            ]}>
                            <OmiMark />
                            <Text style={styles.greeting}>I’m ready.</Text>
                            <View style={styles.currents}>
                              <Text style={styles.sectionLabel}>CURRENTS</Text>
                              {chatError === null ? (
                                <Text style={styles.empty}>
                                  Nothing’s waiting on you.
                                </Text>
                              ) : (
                                <Text style={styles.error}>{chatError}</Text>
                              )}
                            </View>
                            <View
                              style={[
                                styles.prompts,
                                compact && styles.promptsCompact,
                              ]}>
                              {quickPrompts.map(prompt => (
                                <FocusPressable
                                  accessibilityRole="button"
                                  key={prompt}
                                  onPress={() => setDraft(prompt)}
                                  style={({pressed}) => [
                                    styles.promptChip,
                                    compact && styles.promptChipCompact,
                                    pressed && styles.pressed,
                                  ]}>
                                  <Text style={styles.promptText}>
                                    {prompt}
                                  </Text>
                                </FocusPressable>
                              ))}
                            </View>
                          </Animated.View>
                        ) : (
                          <View style={styles.currents}>
                            <Text style={styles.sectionLabel}>CURRENTS</Text>
                            <View style={styles.transcript}>
                              {hasOlderChat && olderChatCursor !== null && (
                                <FocusPressable
                                  accessibilityLabel="Load older messages"
                                  accessibilityRole="button"
                                  disabled={loadingOlderChat}
                                  onPress={loadOlderMessages}
                                  style={({pressed}) => [
                                    styles.loadOlderButton,
                                    pressed && styles.pressed,
                                  ]}>
                                  <Text style={styles.loadOlderText}>
                                    {loadingOlderChat
                                      ? 'Loading older…'
                                      : 'Load older'}
                                  </Text>
                                </FocusPressable>
                              )}
                              {messages.map(message => (
                                <ChatMessageRow
                                  animate={shouldAnimateChatMessage(message.id)}
                                  compact={compact}
                                  key={message.id}
                                  message={message}
                                  reduceMotion={reduceMotion}
                                />
                              ))}
                              {chatBusy && (
                                <ChatThinking reduceMotion={reduceMotion} />
                              )}
                              {chatError !== null && (
                                <Text style={styles.error}>{chatError}</Text>
                              )}
                            </View>
                          </View>
                        )}
                      </View>
                    </ScrollView>
                  ) : route === 'Conversations' ? (
                    <ConversationsPage
                      loading={readsPhase === 'initial-loading'}
                      outcome={routeOutcome}
                    />
                  ) : route === 'Memories' ? (
                    <MemoriesPage
                      loading={readsPhase === 'initial-loading'}
                      outcome={routeOutcome}
                    />
                  ) : (
                    <TasksPage
                      loading={readsPhase === 'initial-loading'}
                      outcome={routeOutcome}
                    />
                  )}
                </View>
              </Animated.View>
              {route === 'Chat' && composer}
            </KeyboardAvoidingView>
          </View>
        </View>
        {compact && !macDesktop && nav}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  outer: {backgroundColor: '#141414', flex: 1},
  macOuter: {backgroundColor: 'transparent'},
  shell: {backgroundColor: '#141414', flex: 1},
  shellWide: {flexDirection: 'row'},
  macShell: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    paddingTop: 32,
  },
  macTopNavFrame: {
    alignSelf: 'center',
    borderRadius: 22,
    height: 52,
  },
  macTopNav: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderRadius: 22,
    flexDirection: 'row',
    gap: 2,
    height: 52,
    padding: 4,
  },
  macTopNavItem: {
    alignItems: 'center',
    borderRadius: 22,
    flexDirection: 'row',
    gap: 7,
    height: 44,
    paddingHorizontal: 14,
  },
  macTopNavItemActive: {backgroundColor: '#ffffff'},
  macTopNavText: {color: '#505050', fontSize: 13, fontWeight: '600'},
  macTopNavTextActive: {color: '#141414'},
  navigation: {backgroundColor: '#141414'},
  rail: {paddingHorizontal: 8, paddingVertical: 24},
  railHeader: {alignItems: 'flex-start', gap: 8},
  railHeaderExpanded: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  railToggle: {
    alignItems: 'center',
    borderRadius: 12,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  wordmark: {
    color: '#ffffff',
    fontSize: 25,
    fontWeight: '900',
    letterSpacing: -1,
    paddingHorizontal: 2,
  },
  navItems: {gap: 4, marginTop: 32},
  navItemsCompact: {flexDirection: 'row', marginTop: 0},
  navItem: {
    alignItems: 'center',
    borderRadius: 12,
    flexDirection: 'row',
    gap: 12,
    minHeight: 48,
    paddingHorizontal: 18,
  },
  navItemCompact: {
    flex: 1,
    flexDirection: 'column',
    gap: 2,
    justifyContent: 'center',
    paddingHorizontal: 2,
  },
  navItemActive: {backgroundColor: '#ffffff'},
  activePill: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    height: 48,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  activePillHidden: {opacity: 0},
  focusRing: {borderColor: '#ffffff', borderWidth: 2},
  navText: {color: '#b0b0b0', fontSize: 14, fontWeight: '600'},
  navTextCollapsed: {opacity: 0, width: 0},
  navTextActive: {color: '#141414'},
  bottomNav: {
    borderTopColor: '#2a2a2a',
    borderTopWidth: 1,
    paddingHorizontal: 4,
    paddingTop: 4,
  },
  paneInset: {flex: 1, padding: 12},
  macPaneInset: {
    alignSelf: 'stretch',
    paddingBottom: 18,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  paneInsetCompact: {padding: 0},
  paneFrame: {
    flex: 1,
  },
  paneFrameCompact: {},
  paneDepth: {
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  paneDepthLayer: {
    backgroundColor: '#000000',
    borderRadius: 26,
    bottom: -14,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 14,
  },
  paneDepthWide: {opacity: 0.05, transform: [{scaleX: 1.015}]},
  paneDepthMid: {bottom: -10, opacity: 0.07, top: 10},
  paneDepthNear: {bottom: -6, opacity: 0.1, top: 6},
  pane: {
    backgroundColor: '#1a1a1a',
    borderColor: '#303030',
    borderRadius: 26,
    borderWidth: 1,
    flex: 1,
    overflow: 'hidden',
  },
  macPane: {backgroundColor: 'transparent', borderRadius: 22},
  macGlassPanel: {
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  paneCompact: {borderRadius: 0, borderWidth: 0},
  stageMotion: {flex: 1},
  stage: {flexGrow: 1, paddingBottom: 20, paddingHorizontal: 20},
  stageCompact: {paddingHorizontal: 16},
  searchHome: {
    alignSelf: 'center',
    flex: 1,
    maxWidth: 900,
    width: '100%',
  },
  searchHeader: {paddingBottom: 18, paddingTop: 38},
  searchEyebrow: {
    color: '#777777',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
  },
  searchTitle: {
    color: '#ffffff',
    fontSize: 30,
    fontWeight: '600',
    letterSpacing: -0.6,
    marginTop: 8,
  },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#232323',
    borderColor: '#3a3a3a',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginTop: 24,
    minHeight: 58,
    paddingHorizontal: 18,
  },
  searchInput: {color: '#ffffff', flex: 1, fontSize: 15, minHeight: 48},
  clearSearch: {
    alignItems: 'center',
    borderRadius: 22,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  clearSearchText: {color: '#b0b0b0', fontSize: 24, lineHeight: 26},
  searchActions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
    marginTop: 14,
  },
  filters: {flexDirection: 'row', flexWrap: 'wrap', gap: 7},
  filterChip: {
    borderColor: '#363636',
    borderRadius: 18,
    borderWidth: 1,
    minHeight: 36,
    paddingHorizontal: 13,
    justifyContent: 'center',
  },
  filterChipActive: {backgroundColor: '#ffffff', borderColor: '#ffffff'},
  filterText: {color: '#a0a0a0', fontSize: 12, fontWeight: '600'},
  filterTextActive: {color: '#141414'},
  chatPill: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 20,
    flexDirection: 'row',
    gap: 7,
    minHeight: 40,
    paddingHorizontal: 15,
  },
  chatPillText: {color: '#141414', fontSize: 13, fontWeight: '700'},
  timelineLabel: {
    color: '#777777',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginTop: 28,
  },
  chatScroll: {flex: 1},
  chatScrollContent: {flexGrow: 1},
  chatHistory: {
    alignSelf: 'center',
    flex: 1,
    maxWidth: 760,
    minHeight: 500,
    paddingBottom: 40,
    paddingTop: 72,
    width: '100%',
  },
  chatHistoryCompact: {paddingTop: 64},
  home: {
    alignSelf: 'center',
    flex: 1,
    justifyContent: 'center',
    maxWidth: 560,
    minHeight: 500,
    paddingVertical: 40,
    width: '100%',
  },
  homeCompact: {paddingVertical: 32},
  restingStage: {alignItems: 'center', width: '100%'},
  backButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 4,
    minHeight: 40,
    paddingHorizontal: 4,
    position: 'absolute',
    top: 18,
  },
  backButtonText: {color: '#b0b0b0', fontSize: 13, fontWeight: '600'},
  mark: {
    alignItems: 'center',
    alignSelf: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  markImage: {borderRadius: 20, height: 40, width: 40},
  greeting: {
    color: '#ffffff',
    fontSize: 25,
    fontWeight: '600',
    marginTop: 20,
    textAlign: 'center',
  },
  currents: {marginTop: 34, width: '100%'},
  sectionLabel: {
    color: '#888888',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 12,
  },
  prompts: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'center',
    marginTop: 28,
  },
  promptsCompact: {alignSelf: 'stretch'},
  promptChip: {
    alignItems: 'center',
    backgroundColor: '#252525',
    borderColor: '#363636',
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 14,
  },
  promptChipCompact: {flexBasis: '48%', flexGrow: 1, paddingHorizontal: 12},
  promptText: {
    color: '#e5e5e5',
    fontSize: 13,
    fontWeight: '500',
    textAlign: 'center',
  },
  empty: {color: '#666666', fontSize: 12, textAlign: 'center'},
  transcript: {gap: 24},
  loadOlderButton: {
    alignItems: 'center',
    alignSelf: 'center',
    borderColor: '#484848',
    borderRadius: 18,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 18,
  },
  loadOlderText: {color: '#b0b0b0', fontSize: 13, fontWeight: '600'},
  message: {color: '#e5e5e5', fontSize: 14, lineHeight: 20},
  chatMessageRow: {flexDirection: 'row', width: '100%'},
  chatMessageRowHuman: {justifyContent: 'flex-end'},
  chatMessageRowAi: {
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'flex-start',
  },
  chatMessageColumn: {minWidth: 0},
  chatMessageColumnCompact: {maxWidth: '85%'},
  chatMessageColumnDesktop: {maxWidth: '75%'},
  chatMessageColumnHuman: {alignItems: 'flex-end'},
  chatBubble: {borderRadius: 16, paddingHorizontal: 20, paddingVertical: 12},
  chatBubbleHuman: {backgroundColor: '#2c2c33'},
  chatBubbleAi: {
    backgroundColor: '#202020',
    borderColor: '#343434',
    borderWidth: 1,
  },
  chatAvatar: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    position: 'relative',
    width: 40,
  },
  chatAvatarDot: {
    backgroundColor: '#ffffff',
    borderRadius: 3,
    height: 5,
    position: 'absolute',
    width: 5,
  },
  chatAvatarDotTop: {left: 17.5, top: 3.5},
  chatAvatarDotTopRight: {left: 27.5, top: 7.5},
  chatAvatarDotRight: {left: 31.5, top: 17.5},
  chatAvatarDotBottomRight: {left: 27.5, top: 27.5},
  chatAvatarDotBottom: {left: 17.5, top: 31.5},
  chatAvatarDotBottomLeft: {left: 7.5, top: 27.5},
  chatAvatarDotLeft: {left: 3.5, top: 17.5},
  chatAvatarDotTopLeft: {left: 7.5, top: 7.5},
  chatTimestamp: {color: '#666666', fontSize: 12, marginTop: 4},
  chatTimestampHuman: {textAlign: 'right'},
  cancelledMessage: {borderColor: '#666666', opacity: 0.72},
  cancelledLabel: {color: '#888888', fontSize: 11, marginTop: 4},
  failedLabel: {color: '#d8a0a0', fontSize: 12, marginTop: 4},
  thinkingText: {color: '#888888', fontSize: 12},
  thinkingDots: {flexDirection: 'row', gap: 5, paddingVertical: 4},
  thinkingDot: {
    backgroundColor: '#888888',
    borderRadius: 3,
    height: 6,
    width: 6,
  },
  error: {color: '#d8a0a0', fontSize: 12, textAlign: 'center'},
  memoryPage: {flex: 1, paddingHorizontal: 28, paddingTop: 24},
  memorySearchBox: {
    alignItems: 'center',
    backgroundColor: '#202020',
    borderColor: '#343434',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 9,
    marginTop: 16,
    paddingHorizontal: 14,
  },
  memorySearchInput: {color: '#ffffff', flex: 1, fontSize: 14, minHeight: 44},
  memoryList: {gap: 8, paddingBottom: 28, paddingTop: 14},
  memoryCard: {
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 15,
    paddingVertical: 13,
  },
  memoryMetaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  memoryTimestamp: {color: '#898989', fontSize: 11, fontWeight: '600'},
  memoryCitationCount: {color: '#707070', fontSize: 11},
  memoryBody: {
    color: '#eeeeee',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
  },
  memoryProvenance: {color: '#888888', fontSize: 11, marginTop: 9},
  memoryCitation: {color: '#707070', fontSize: 11, marginTop: 3},
  memoryFooter: {gap: 10, paddingVertical: 8},
  tasksPage: {flex: 1, paddingHorizontal: 28, paddingTop: 24},
  taskSearchBox: {
    alignItems: 'center',
    backgroundColor: '#202020',
    borderColor: '#343434',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 9,
    marginTop: 16,
    paddingHorizontal: 14,
  },
  taskList: {gap: 20, paddingBottom: 78, paddingTop: 18},
  taskGroup: {gap: 7},
  taskGroupHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 3,
  },
  taskGroupTitle: {
    color: '#d8d8d8',
    fontSize: 13,
    fontWeight: '700',
  },
  taskGroupCount: {color: '#737373', fontSize: 11},
  taskCard: {
    alignItems: 'center',
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 13,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 54,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  taskCardSelected: {backgroundColor: '#292929', borderColor: '#686868'},
  taskCompletion: {
    alignItems: 'center',
    borderColor: '#777777',
    borderRadius: 9,
    borderWidth: 1,
    height: 18,
    justifyContent: 'center',
    width: 18,
  },
  taskCompletionDone: {backgroundColor: '#d8d8d8', borderColor: '#d8d8d8'},
  taskCheck: {color: '#1a1a1a', fontSize: 12, fontWeight: '800'},
  taskCardText: {flex: 1},
  taskDescription: {color: '#eeeeee', fontSize: 14, lineHeight: 19},
  taskDescriptionDone: {
    color: '#858585',
    textDecorationLine: 'line-through',
  },
  taskDue: {color: '#707070', fontSize: 11, marginTop: 3},
  taskShortcuts: {
    alignItems: 'center',
    backgroundColor: '#1d1d1d',
    borderColor: '#303030',
    borderRadius: 13,
    borderWidth: 1,
    bottom: 14,
    flexDirection: 'row',
    gap: 18,
    left: 28,
    paddingHorizontal: 14,
    paddingVertical: 9,
    position: 'absolute',
  },
  taskShortcut: {color: '#858585', fontSize: 11, fontWeight: '600'},
  projection: {flex: 1, paddingHorizontal: 28, paddingVertical: 24},
  projectionTitle: {color: '#ffffff', fontSize: 22, fontWeight: '600'},
  projectionEmpty: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingBottom: 48,
  },
  projectionEmptyTitle: {color: '#e5e5e5', fontSize: 16, fontWeight: '600'},
  projectionEmptyCopy: {
    color: '#888888',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
    textAlign: 'center',
  },
  readStatuses: {gap: 8, paddingTop: 12},
  readStatus: {
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 12,
    borderWidth: 1,
    gap: 3,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  readStatusText: {color: '#b0b0b0', fontSize: 13, fontWeight: '600'},
  retryButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderColor: '#484848',
    borderRadius: 16,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 18,
  },
  retryButtonText: {color: '#ffffff', fontSize: 13, fontWeight: '600'},
  resultList: {flexGrow: 1, gap: 8, paddingBottom: 28},
  resultRow: {
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  resultKindRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  resultKind: {
    color: '#777777',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  resultMeta: {color: '#777777', fontSize: 11},
  resultTitle: {
    color: '#f2f2f2',
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 20,
    marginTop: 7,
  },
  resultSummary: {color: '#888888', fontSize: 12, lineHeight: 17, marginTop: 5},
  conversationPage: {flex: 1, paddingHorizontal: 28, paddingVertical: 24},
  conversationDiscovery: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 9,
    marginTop: 16,
  },
  conversationSearchBox: {
    alignItems: 'center',
    backgroundColor: '#202020',
    borderColor: '#343434',
    borderRadius: 14,
    borderWidth: 1,
    flex: 1,
    flexDirection: 'row',
    gap: 9,
    paddingHorizontal: 14,
  },
  conversationStarFilter: {
    alignItems: 'center',
    borderColor: '#3a3a3a',
    borderRadius: 14,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: 15,
  },
  conversationStarFilterActive: {
    backgroundColor: '#ffffff',
    borderColor: '#ffffff',
  },
  conversationStarFilterText: {
    color: '#a0a0a0',
    fontSize: 12,
    fontWeight: '600',
  },
  conversationStarFilterTextActive: {color: '#141414'},
  conversationContent: {flex: 1, flexDirection: 'row', gap: 16, marginTop: 18},
  conversationListPane: {flex: 1},
  conversationList: {gap: 16, paddingBottom: 28},
  conversationGroup: {gap: 7},
  conversationGroupTitle: {
    color: '#858585',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.7,
    paddingHorizontal: 3,
    textTransform: 'uppercase',
  },
  conversationRow: {
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  conversationRowSelected: {borderColor: '#ffffff'},
  conversationRowMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  conversationRowTime: {color: '#777777', fontSize: 11, fontWeight: '600'},
  conversationRowStar: {color: '#d0d0d0', fontSize: 16, lineHeight: 18},
  conversationRowDuration: {color: '#777777', fontSize: 11, marginTop: 9},
  conversationDetail: {
    backgroundColor: '#202020',
    borderColor: '#303030',
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    padding: 20,
  },
  conversationDetailEmpty: {flex: 1, justifyContent: 'center'},
  conversationDetailEyebrow: {
    color: '#777777',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  conversationDetailTitle: {
    color: '#f2f2f2',
    fontSize: 21,
    fontWeight: '600',
    lineHeight: 27,
    marginTop: 10,
  },
  conversationDetailSummary: {
    color: '#a0a0a0',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
  },
  conversationDetailFields: {gap: 8, marginTop: 22},
  conversationDetailField: {color: '#d0d0d0', fontSize: 13, lineHeight: 18},
  conversationDetailNotice: {
    color: '#777777',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 24,
  },
  composerWrap: {paddingBottom: 16, paddingHorizontal: 20, paddingTop: 12},
  composerWrapCompact: {paddingHorizontal: 16},
  composer: {
    alignSelf: 'center',
    backgroundColor: '#252525',
    borderColor: '#3a3a3a',
    borderRadius: 28,
    borderWidth: 1,
    minHeight: 62,
    paddingHorizontal: 10,
    paddingVertical: 7,
    width: '100%',
  },
  composerFocused: {borderColor: '#626262'},
  composerInput: {
    color: '#ffffff',
    fontSize: 16,
    maxHeight: 200,
    minHeight: 44,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  composerActions: {alignItems: 'center', flexDirection: 'row'},
  iconButton: {
    alignItems: 'center',
    borderRadius: 20,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  actionSpacer: {flex: 1},
  sendButton: {
    alignItems: 'center',
    backgroundColor: '#555555',
    borderRadius: 20,
    height: 44,
    justifyContent: 'center',
    opacity: 0.35,
    width: 44,
  },
  sendButtonEnabled: {backgroundColor: '#ffffff', opacity: 1},
  stopButton: {backgroundColor: '#ffffff', opacity: 1},
  pressed: {opacity: 0.72, transform: [{scale: 0.98}]},
});

export default App;
