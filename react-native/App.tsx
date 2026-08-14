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
  SafeAreaView,
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
import Paperclip from 'lucide-react-native/icons/paperclip';
import Search from 'lucide-react-native/icons/search';
import Square from 'lucide-react-native/icons/square';
import {
  cancelChatGeneration,
  loadChatHistory,
  sendChatMessage,
  type ChatMessage,
} from './src/chatClient';
import {omiBackend} from './src/omiNative';
import {
  loadDesktopReads,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
  type DomainReadOutcome,
  type ReadPageState,
} from './src/desktopReadClient';

type NavigationIcon = React.ComponentType<{
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

function NavItem({
  label,
  icon: Icon,
  compact,
  active,
  onPress,
}: {
  label: string;
  icon: NavigationIcon;
  compact: boolean;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{selected: active}}
      onPress={onPress}
      style={({pressed}) => [
        styles.navItem,
        compact && styles.navItemCompact,
        active && styles.navItemActive,
        pressed && styles.pressed,
      ]}>
      <Icon color={active ? '#141414' : '#888888'} size={20} strokeWidth={2} />
      <Text
        numberOfLines={1}
        style={[
          styles.navText,
          !compact && styles.navTextCollapsed,
          active && styles.navTextActive,
        ]}>
        {label}
      </Text>
    </Pressable>
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
  {label: 'Tasks', value: 'task'},
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
}: {
  items: DesktopReadProjection[];
  loading: boolean;
  error: string | null;
  emptyCopy: string;
  header?: React.ReactElement;
  footer?: React.ReactElement;
}) {
  const renderItem = useCallback(
    ({item}: {item: DesktopReadProjection}) => <ProjectionRow item={item} />,
    [],
  );
  const keyExtractor = useCallback(
    (item: DesktopReadProjection) => `${item.kind}:${item.id}`,
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
        {error === null ? 'Nothing to show yet' : 'Unable to load'}
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
  const compact = width < 760;
  const stageOpacity = useRef(new Animated.Value(0)).current;
  const stageTranslateY = useRef(new Animated.Value(8)).current;
  const mobileNavOpacity = useRef(new Animated.Value(0)).current;
  const mobileNavTranslateY = useRef(new Animated.Value(100)).current;
  const [reduceMotion, setReduceMotion] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(
    null,
  );
  const [chatError, setChatError] = useState<string | null>(null);
  const [route, setRoute] = useState<Route>('Home');
  const [readOutcomes, setReadOutcomes] = useState<DesktopReadOutcomes | null>(
    null,
  );
  const [readsLoading, setReadsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [projectionFilter, setProjectionFilter] =
    useState<ProjectionFilter>('all');

  useEffect(() => {
    let active = true;
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      return () => undefined;
    }
    loadChatHistory(backend)
      .then(history => {
        if (active) {
          setMessages(history);
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

  useEffect(() => {
    let active = true;
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      setReadsLoading(false);
      const unavailable = {
        status: 'error',
        error: 'Backend unavailable',
      } as const;
      setReadOutcomes({
        conversations: unavailable,
        memories: unavailable,
        tasks: unavailable,
      });
      return () => undefined;
    }
    loadDesktopReads(backend)
      .then(outcomes => {
        if (active) {
          setReadOutcomes(outcomes);
        }
      })
      .catch(() => {
        if (active) {
          const failed = {
            status: 'error',
            error: 'Desktop history could not be loaded.',
          } as const;
          setReadOutcomes({
            conversations: failed,
            memories: failed,
            tasks: failed,
          });
        }
      })
      .finally(() => {
        if (active) {
          setReadsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

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
      ...(readOutcomes.tasks.status === 'success'
        ? readOutcomes.tasks.value.items
        : []),
    ];
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

  const nav = (
    <Animated.View
      accessibilityRole="tablist"
      style={[
        styles.navigation,
        compact ? styles.bottomNav : styles.rail,
        compact && {
          opacity: mobileNavOpacity,
          transform: [{translateY: mobileNavTranslateY}],
        },
      ]}>
      {!compact && <Text style={styles.wordmark}>omi</Text>}
      <View style={[styles.navItems, compact && styles.navItemsCompact]}>
        {navigation.map(item => (
          <NavItem
            active={
              route === item.label ||
              (route === 'Chat' && item.label === 'Home')
            }
            compact={compact}
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
    try {
      const result = await sendChatMessage(backend, text, Date.now(), id => {
        setActiveGenerationId(id);
      });
      setMessages(current => [
        ...current.filter(message => message.id !== result.human.id),
        result.human,
        ...(result.assistant === null ? [] : [result.assistant]),
      ]);
      setDraft('');
    } catch {
      setChatError('Message not sent. Try again.');
      try {
        setMessages(await loadChatHistory(backend));
      } catch {}
    } finally {
      setActiveGenerationId(null);
      setChatBusy(false);
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
      <View style={styles.composer}>
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
          <Pressable
            accessibilityLabel="Attach file unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Paperclip color="#666666" size={18} strokeWidth={2} />
          </Pressable>
          <Pressable
            accessibilityLabel="Dictation unavailable"
            accessibilityRole="button"
            disabled
            style={({pressed}) => [
              styles.iconButton,
              pressed && styles.pressed,
            ]}>
            <Mic color="#666666" size={18} strokeWidth={2} />
          </Pressable>
          <View style={styles.actionSpacer} />
          <Pressable
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
          </Pressable>
        </View>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.outer}>
      <View style={[styles.shell, !compact && styles.shellWide]}>
        {!compact && nav}
        <View style={[styles.paneInset, compact && styles.paneInsetCompact]}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={[styles.pane, compact && styles.paneCompact]}>
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
                      emptyCopy="Nothing matches this search yet."
                      error={null}
                      footer={
                        readOutcomes === null ? undefined : (
                          <View style={styles.readStatuses}>
                            <OutcomeStatus
                              label="Conversations"
                              outcome={readOutcomes.conversations}
                            />
                            <OutcomeStatus
                              label="Memories"
                              outcome={readOutcomes.memories}
                            />
                            <OutcomeStatus
                              label="Tasks"
                              outcome={readOutcomes.tasks}
                            />
                          </View>
                        )
                      }
                      header={
                        <View style={styles.searchHeader}>
                          <Text style={styles.searchEyebrow}>HOME</Text>
                          <Text style={styles.searchTitle}>
                            Search what you’ve seen and heard
                          </Text>
                          <View style={styles.searchBox}>
                            <Search color="#888888" size={18} strokeWidth={2} />
                            <TextInput
                              accessibilityLabel="Search Home"
                              onChangeText={setSearchQuery}
                              placeholder="Search conversations, memories, and tasks"
                              placeholderTextColor="#777777"
                              style={styles.searchInput}
                              value={searchQuery}
                            />
                          </View>
                          <View style={styles.searchActions}>
                            <View style={styles.filters}>
                              {filterLabels.map(filter => (
                                <Pressable
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
                                </Pressable>
                              ))}
                            </View>
                            <Pressable
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
                            </Pressable>
                          </View>
                          <Text style={styles.timelineLabel}>LATEST</Text>
                        </View>
                      }
                      items={homeResults}
                      loading={readsLoading}
                    />
                  </View>
                ) : route === 'Chat' ? (
                  <View style={styles.home}>
                    <Pressable
                      accessibilityLabel="Back to Home"
                      accessibilityRole="button"
                      onPress={() => setRoute('Home')}
                      style={({pressed}) => [
                        styles.backButton,
                        pressed && styles.pressed,
                      ]}>
                      <ChevronLeft color="#b0b0b0" size={18} strokeWidth={2} />
                      <Text style={styles.backButtonText}>Home</Text>
                    </Pressable>
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
                          {messages.map(message => (
                            <Text
                              key={message.id}
                              style={[
                                styles.message,
                                message.sender === 'human' &&
                                  styles.humanMessage,
                              ]}>
                              {message.text}
                            </Text>
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
                        <Pressable
                          accessibilityRole="button"
                          key={prompt}
                          onPress={() => setDraft(prompt)}
                          style={({pressed}) => [
                            styles.promptChip,
                            pressed && styles.pressed,
                          ]}>
                          <Text style={styles.promptText}>{prompt}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ) : (
                  <ProjectionPage
                    loading={readsLoading}
                    outcome={routeOutcome}
                    route={route}
                  />
                )}
              </View>
            </Animated.View>
            {route === 'Chat' && composer}
          </KeyboardAvoidingView>
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
  rail: {paddingHorizontal: 8, paddingVertical: 24, width: 72},
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
  message: {color: '#e5e5e5', fontSize: 14, lineHeight: 20},
  humanMessage: {color: '#ffffff', fontWeight: '600'},
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
  composerWrap: {paddingBottom: 16, paddingHorizontal: 20, paddingTop: 12},
  composer: {
    alignSelf: 'center',
    backgroundColor: '#252525',
    borderColor: '#3a3a3a',
    borderRadius: 28,
    borderWidth: 1,
    maxWidth: 820,
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
