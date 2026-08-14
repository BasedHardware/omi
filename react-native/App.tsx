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
  KeyboardAvoidingView,
  Platform,
  Pressable,
  type PressableProps,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
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
  loadDesktopReads,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
  type ConversationProjection,
  type DomainReadOutcome,
  type ReadPageState,
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
type Route = 'Home' | 'Chat' | 'Conversations' | 'Memories' | 'Tasks';
type ReadRoute = Exclude<Route, 'Home' | 'Chat'>;
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
      <View style={[styles.markBar, styles.markBarShort]} />
      <View style={[styles.markBar, styles.markBarTall]} />
      <View style={[styles.markBar, styles.markBarMedium]} />
      <View style={[styles.markBar, styles.markBarTall]} />
      <View style={[styles.markBar, styles.markBarShort]} />
    </View>
  );
}

const filterLabels: Array<{label: string; value: ProjectionFilter}> = [
  {label: 'All', value: 'all'},
  {label: 'Conversations', value: 'conversation'},
  {label: 'Memories', value: 'memory'},
];

function projectionKind(route: ReadRoute): DesktopReadProjection['kind'] {
  return {
    Conversations: 'conversation',
    Memories: 'memory',
    Tasks: 'task',
  }[route] as DesktopReadProjection['kind'];
}

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
          {formatConversationDate(item.startedAt)}
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
  const selected = conversations.find(item => item.id === selectedId) ?? null;
  const error = outcome?.status === 'error' ? outcome.error : null;
  const renderItem = useCallback(
    ({item}: {item: ConversationProjection}) => (
      <ConversationRow
        item={item}
        onPress={() => setSelectedId(item.id)}
        selected={selectedId === item.id}
      />
    ),
    [selectedId],
  );
  const keyExtractor = useCallback(
    (item: ConversationProjection) => item.id,
    [],
  );
  const empty = loading ? (
    <View style={styles.projectionEmpty}>
      <ActivityIndicator color="#888888" />
      <Text style={styles.projectionEmptyCopy}>Loading…</Text>
    </View>
  ) : (
    <View style={styles.projectionEmpty}>
      <Text style={styles.projectionEmptyTitle}>
        {error === null ? 'No conversations yet.' : 'Unable to load'}
      </Text>
      <Text style={styles.projectionEmptyCopy}>
        {error ?? 'No conversations are available in this loaded page.'}
      </Text>
    </View>
  );

  return (
    <View style={styles.conversationPage}>
      <Text style={styles.projectionTitle}>Conversations</Text>
      <View style={styles.conversationContent}>
        <FlatList
          contentContainerStyle={styles.conversationList}
          data={conversations}
          keyExtractor={keyExtractor}
          ListEmptyComponent={empty}
          ListFooterComponent={
            outcome?.status === 'success' ? (
              <ReadStatus label="Conversations" page={outcome.value.page} />
            ) : null
          }
          renderItem={renderItem}
          style={styles.conversationListPane}
        />
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
      {page.reasons.length > 0 && (
        <Text style={styles.readStatusReason}>{page.reasons.join(', ')}</Text>
      )}
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
      <Text style={styles.readStatusReason}>{outcome.error}</Text>
    </View>
  ) : (
    <ReadStatus label={label} page={outcome.value.page} />
  );
}

function ProjectionPage({
  route,
  outcome,
  loading,
}: {
  route: ReadRoute;
  outcome: DomainReadOutcome<DesktopReadProjection> | null;
  loading: boolean;
}) {
  const items = outcome?.status === 'success' ? outcome.value.items : [];
  const error = outcome?.status === 'error' ? outcome.error : null;
  return (
    <View style={styles.projection}>
      <Text style={styles.projectionTitle}>{route}</Text>
      <ProjectionList
        emptyCopy={`No ${route.toLowerCase()} yet.`}
        error={error}
        footer={
          outcome?.status === 'success' ? (
            <ReadStatus label={route} page={outcome.value.page} />
          ) : undefined
        }
        items={items.filter(item => item.kind === projectionKind(route))}
        loading={loading}
      />
    </View>
  );
}

function App(): React.JSX.Element {
  const {width} = useWindowDimensions();
  const compact = width < 1024;
  const floatingPane = width >= 640;
  const composerMaxWidth = width >= 1280 ? 820 : width >= 768 ? 720 : 640;
  const stageOpacity = useRef(new Animated.Value(0)).current;
  const stageTranslateY = useRef(new Animated.Value(8)).current;
  const mobileNavOpacity = useRef(new Animated.Value(0)).current;
  const mobileNavTranslateY = useRef(new Animated.Value(100)).current;
  const activePillTranslateY = useRef(new Animated.Value(0)).current;
  const railWidth = useRef(new Animated.Value(72)).current;
  const [reduceMotion, setReduceMotion] = useState(false);
  const [railExpanded, setRailExpanded] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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
  }, []);

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
            expanded={railExpanded}
            icon={item.icon}
            key={item.label}
            label={item.label}
            onPress={() => setRoute(item.label as Route)}
          />
        ))}
      </View>
    </Animated.View>
  );

  const send = async () => {
    const text = draft.trim();
    const backend = omiBackend;
    if (backend === undefined || backend === null || text === '' || chatBusy) {
      return;
    }
    setChatBusy(true);
    setChatError(null);
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

  const composer = (
    <View style={styles.composerWrap}>
      <View style={[styles.composer, {maxWidth: composerMaxWidth}]}>
        <TextInput
          accessibilityLabel="Ask Omi"
          multiline
          onChangeText={setDraft}
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
    <SafeAreaView style={styles.outer}>
      <View style={[styles.shell, !compact && styles.shellWide]}>
        {!compact && nav}
        <View
          style={[styles.paneInset, !floatingPane && styles.paneInsetCompact]}>
          <View
            accessibilityLabel="Floating pane"
            style={[
              styles.paneFrame,
              !floatingPane && styles.paneFrameCompact,
            ]}>
            {floatingPane && (
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
              style={[styles.pane, !floatingPane && styles.paneCompact]}>
              <Animated.View
                accessibilityLabel={`${route} stage`}
                style={[
                  styles.stageMotion,
                  {
                    opacity: stageOpacity,
                    transform: [{translateY: stageTranslateY}],
                  },
                ]}>
                <View style={styles.stage}>
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
                      style={styles.chatScroll}>
                      <View style={styles.home}>
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
                        <OmiMark />
                        <Text style={styles.greeting}>I’m ready.</Text>
                        <View style={styles.currents}>
                          <Text style={styles.sectionLabel}>CURRENTS</Text>
                          {messages.length === 0 &&
                          !chatBusy &&
                          chatError === null ? (
                            <Text style={styles.empty}>
                              Nothing’s waiting on you.
                            </Text>
                          ) : (
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
                                <View
                                  accessibilityLabel={
                                    message.generationOutcome === 'failed'
                                      ? 'Failed response'
                                      : undefined
                                  }
                                  key={message.id}>
                                  {message.generationOutcome !== 'failed' && (
                                    <Text
                                      style={[
                                        styles.message,
                                        message.sender === 'human' &&
                                          styles.humanMessage,
                                        message.generationOutcome ===
                                          'cancelled' &&
                                          styles.cancelledMessage,
                                      ]}>
                                      {message.text}
                                    </Text>
                                  )}
                                  {message.generationOutcome ===
                                    'cancelled' && (
                                    <Text style={styles.cancelledLabel}>
                                      Response stopped
                                    </Text>
                                  )}
                                  {message.generationOutcome === 'failed' && (
                                    <Text style={styles.failedLabel}>
                                      {message.generationRetryable === true
                                        ? 'Response failed. Try again.'
                                        : 'Response failed.'}
                                    </Text>
                                  )}
                                </View>
                              ))}
                              {chatBusy && (
                                <Text style={styles.empty}>Thinking…</Text>
                              )}
                              {chatError !== null && (
                                <Text style={styles.error}>{chatError}</Text>
                              )}
                            </View>
                          )}
                        </View>
                        <View style={styles.prompts}>
                          {quickPrompts.map(prompt => (
                            <FocusPressable
                              accessibilityRole="button"
                              key={prompt}
                              onPress={() => setDraft(prompt)}
                              style={({pressed}) => [
                                styles.promptChip,
                                pressed && styles.pressed,
                              ]}>
                              <Text style={styles.promptText}>{prompt}</Text>
                            </FocusPressable>
                          ))}
                        </View>
                      </View>
                    </ScrollView>
                  ) : route === 'Conversations' ? (
                    <ConversationsPage
                      loading={readsPhase === 'initial-loading'}
                      outcome={routeOutcome}
                    />
                  ) : (
                    <ProjectionPage
                      loading={readsPhase === 'initial-loading'}
                      outcome={routeOutcome}
                      route={route}
                    />
                  )}
                </View>
              </Animated.View>
              {route === 'Chat' && composer}
            </KeyboardAvoidingView>
          </View>
        </View>
        {compact && nav}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  outer: {backgroundColor: '#141414', flex: 1},
  shell: {backgroundColor: '#141414', flex: 1},
  shellWide: {flexDirection: 'row'},
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
  paneCompact: {borderRadius: 0, borderWidth: 0},
  stageMotion: {flex: 1},
  stage: {flexGrow: 1, paddingBottom: 20, paddingHorizontal: 20},
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
  home: {
    alignSelf: 'center',
    flex: 1,
    justifyContent: 'center',
    maxWidth: 560,
    minHeight: 500,
    paddingVertical: 40,
    width: '100%',
  },
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
    flexDirection: 'row',
    gap: 3,
    height: 34,
  },
  markBar: {backgroundColor: '#ffffff', borderRadius: 4, width: 5},
  markBarShort: {height: 11},
  markBarMedium: {height: 20},
  markBarTall: {height: 30},
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
  promptText: {color: '#e5e5e5', fontSize: 13, fontWeight: '500'},
  empty: {color: '#666666', fontSize: 12, textAlign: 'center'},
  transcript: {gap: 10},
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
  humanMessage: {color: '#ffffff', fontWeight: '600'},
  cancelledMessage: {borderColor: '#666666', opacity: 0.72},
  cancelledLabel: {color: '#888888', fontSize: 11, marginTop: 4},
  failedLabel: {color: '#d8a0a0', fontSize: 12, marginTop: 4},
  error: {color: '#d8a0a0', fontSize: 12, textAlign: 'center'},
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
  readStatusReason: {color: '#777777', fontSize: 12},
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
  conversationContent: {flex: 1, flexDirection: 'row', gap: 16, marginTop: 18},
  conversationListPane: {flex: 1},
  conversationList: {gap: 8, paddingBottom: 28},
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
  composerInput: {
    color: '#ffffff',
    fontSize: 16,
    maxHeight: 140,
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
  stopButton: {opacity: 1},
  pressed: {opacity: 0.72, transform: [{scale: 0.98}]},
});

export default App;
