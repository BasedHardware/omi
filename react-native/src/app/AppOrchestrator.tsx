import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  Keyboard,
  KeyboardAvoidingView,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  ScrollView,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import omiPendant from '../../assets/omi-pendant.webp';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
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
} from '../chatClient';
import {omiBackend} from '../omiNative';
import {
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopRecoveryCopy,
} from '../desktopReadClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import {styles} from '../ui/styles';
import {OutcomeStatus} from '../ui/ReadStatus';
import {ProjectionList, ProjectionRow} from '../ui/ProjectionList';
import {HomeRecovery} from '../ui/Recovery';
import {HomeTimeline} from '../ui/Timeline';
import {HomeSearchField} from '../ui/SearchField';
import {Toolbar} from '../ui/Toolbar';
import {Sheet} from '../ui/Sheet';
import {Onboarding} from '../ui/Onboarding';
import {PageShell} from '../ui/PageShell';
import {FocusPressable} from '../ui/Pressable';
import {ConversationsPage} from '../pages/Conversations';
import {MemoriesPage} from '../pages/Memories';
import {TasksPage} from '../pages/Tasks';
import {ConnectorsPage} from '../pages/Connectors';
import {SettingsPage} from '../pages/Settings';
import {HomeSurface} from '../pages/Home';
import {resolveInitialRoute, type Route} from './routes';
import {DeviceSession, homeConnectionStatus} from './DeviceSession';
import {useDesktopReads} from './useDesktopReads';
import {useOnboarding} from './useOnboarding';
import {useNativeDevices} from './useNativeDevices';
import {useReduceMotion} from './useReduceMotion';
import {omiDotColor} from '../ui/OmiAvatar';
import {OmiMark, bundledAssetSource} from '../ui/OmiMark';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {AppNav} from '../ui/AppNav';
import {Composer} from '../ui/Composer';

export {omiDotColor};

type AppProps = {initialRoute?: string};

const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];

function App({initialRoute}: AppProps): React.JSX.Element {
  const {width} = useWindowDimensions();
  const macDesktop = Platform.OS === 'macos';
  const compact = width < 1024;
  const desktopWorkspace = macDesktop;
  const floatingPane = width >= 640;
  const composerMaxWidth = width >= 1280 ? 820 : width >= 768 ? 720 : 640;
  const stageOpacity = useRef(new Animated.Value(0)).current;
  const stageTranslateY = useRef(new Animated.Value(8)).current;
  const homeResultsOpacity = useRef(new Animated.Value(0)).current;
  const restingOpacity = useRef(new Animated.Value(0)).current;
  const restingTranslateY = useRef(new Animated.Value(8)).current;
  const reduceMotion = useReduceMotion();
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const stableChatMessageIds = useRef(new Set<string>()).current;
  const animatedChatMessageIds = useRef(new Set<string>()).current;
  const chatScrollRef = useRef<ScrollView>(null);
  const composerRef = useRef<TextInput>(null);
  const shouldFollowChat = useRef(false);
  const [olderChatCursor, setOlderChatCursor] = useState<string | null>(null);
  const [hasOlderChat, setHasOlderChat] = useState(false);
  const [loadingOlderChat, setLoadingOlderChat] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(
    null,
  );
  const [chatError, setChatError] = useState<string | null>(null);
  const [route, setRoute] = useState<Route>(() =>
    resolveInitialRoute(initialRoute),
  );
  const [homeChatOpen, setHomeChatOpen] = useState(false);
  const {
    allHomeReadsUnavailable,
    homeReadsLoadedRef,
    readOutcomes,
    reads,
    readsPhase,
    refreshReads,
  } = useDesktopReads();
  const {
    completeFirstRun,
    onboardingRequired,
    signInAndRefresh,
    signOutAndRefresh,
    signingIn,
  } = useOnboarding(macDesktop, refreshReads);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchArmed, setSearchArmed] = useState(false);
  const [macMenuOpen, setMacMenuOpen] = useState(false);
  const [homeSearchFocusNonce, setHomeSearchFocusNonce] = useState(0);
  const [composerFocused, setComposerFocused] = useState(false);
  const {
    deviceBusy,
    deviceScanMessage,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  } = useNativeDevices();
  const searchRef = useRef<TextInput>(null);
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
    if (route === 'Home') {
      Keyboard?.dismiss?.();
    }
  }, [route]);

  useEffect(() => {
    if (route === 'Home' && homeChatOpen && shouldFollowChat.current) {
      chatScrollRef.current?.scrollToEnd({animated: !reduceMotion});
    }
  }, [chatBusy, homeChatOpen, messages, reduceMotion, route]);

  const routeOutcome = useMemo(() => {
    if (readOutcomes === null || route === 'Home') {
      return null;
    }
    const outcomes = {
      Conversations: readOutcomes.conversations,
      Memories: readOutcomes.memories,
      Tasks: readOutcomes.tasks,
    };
    return route === 'Conversations' ||
      route === 'Memories' ||
      route === 'Tasks'
      ? outcomes[route]
      : null;
  }, [readOutcomes, route]);

  const homeResults = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return reads.filter(
      item =>
        query === '' || item.searchableText.toLocaleLowerCase().includes(query),
    );
  }, [reads, searchQuery]);
  const homeSearching = searchQuery.trim() !== '';
  // An unavailable Omi cloud read is a single truthful empty state, not a result row. Keeping the
  // results panel content-sized here preserves the upstream two-island hierarchy instead of
  // turning an error into a window-filling modal.
  const homeSpineHasRows = homeResults.length > 0 && !allHomeReadsUnavailable;
  useEffect(() => {
    homeResultsOpacity.setValue(0);
    if (!homeSearching) {
      return;
    }
    Animated.timing(homeResultsOpacity, {
      duration: reduceMotion ? 1 : 180,
      easing: Easing.out(Easing.cubic),
      toValue: 1,
      useNativeDriver: true,
    }).start();
  }, [homeResultsOpacity, homeSearching, reduceMotion]);

  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setRoute('Home');
      setHomeChatOpen(false);
      setHomeSearchFocusNonce(current => current + 1);
    });
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (homeSearchFocusNonce === 0) {
      return;
    }
    searchRef.current?.focus();
  }, [homeSearchFocusNonce]);

  useEffect(() => {
    if (reduceMotion) {
      stageOpacity.setValue(1);
      stageTranslateY.setValue(0);
      return;
    }
    stageOpacity.setValue(0);
    stageTranslateY.setValue(8);
    Animated.parallel([
      Animated.timing(stageOpacity, {
        duration: 180,
        easing: Easing.bezier(0.22, 1, 0.36, 1),
        toValue: 1,
        // Keep first content paint on the JS driver: the native driver can
        // leave this gate at zero during a cold Fabric launch.
        useNativeDriver: false,
      }),
      Animated.timing(stageTranslateY, {
        duration: 180,
        easing: Easing.bezier(0.22, 1, 0.36, 1),
        toValue: 0,
        useNativeDriver: false,
      }),
    ]).start();
  }, [reduceMotion, route, stageOpacity, stageTranslateY]);

  useEffect(() => {
    if (
      !homeChatOpen ||
      route !== 'Home' ||
      messages.length !== 0 ||
      chatBusy
    ) {
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
    homeChatOpen,
    messages.length,
    reduceMotion,
    restingOpacity,
    restingTranslateY,
    route,
  ]);

  const nav = (
    <AppNav
      compact={compact}
      onNavigate={destination => {
        setRoute(destination);
        if (destination === 'Home') {
          setHomeChatOpen(false);
        }
      }}
      reduceMotion={reduceMotion}
      route={route}
    />
  );

  const macDesktopNav = (
    <Toolbar
      inputRef={searchRef}
      menuOpen={macMenuOpen}
      onOpenChat={() => {
        setRoute('Home');
        setHomeChatOpen(true);
      }}
      onQueryChange={value => {
        setRoute('Home');
        setHomeChatOpen(false);
        setSearchQuery(value);
      }}
      onSearchBlur={() => setSearchFocused(false)}
      onSearchFocus={() => setSearchFocused(true)}
      onSearchPress={() => setSearchArmed(true)}
      onToggleMenu={() => setMacMenuOpen(value => !value)}
      query={searchQuery}
      route={route}
      searchArmed={searchArmed}
      searchFocused={searchFocused}
    />
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
    <Composer
      activeGenerationId={activeGenerationId}
      chatBusy={chatBusy}
      compact={compact}
      composerFocused={composerFocused}
      composerMaxWidth={composerMaxWidth}
      composerRef={composerRef}
      draft={draft}
      onDraftChange={setDraft}
      onFocusChange={setComposerFocused}
      onSend={() => {
        send().catch(() => undefined);
      }}
      onStop={() => {
        stopGeneration().catch(() => undefined);
      }}
    />
  );

  const {
    connectedDevice,
    label: homeStatus,
    color: homeStatusColor,
  } = homeConnectionStatus(nativeSnapshot);
  const bluetoothStatusColor =
    nativeSnapshot === null
      ? '#b4ad9f'
      : nativeSnapshot.bluetooth === 'poweredOn'
      ? '#45b79b'
      : '#d9826f';
  const currentItems = reads.slice(0, 2);

  const homeDesktopReadStatus = (
    <View style={styles.macHomeReadStatuses}>
      {readsPhase !== 'ready' &&
        readsPhase !== 'initial-loading' &&
        readsPhase !== 'unavailable' && (
          <View style={styles.macHomeReadStatus}>
            <Text style={styles.macHomeReadStatusText}>
              {readsPhase === 'refreshing'
                ? 'Refreshing saved data…'
                : 'Showing saved data. Could not refresh.'}
            </Text>
            {readsPhase === 'saved-but-refresh-failed' && (
              <FocusPressable
                accessibilityLabel="Retry saved data"
                accessibilityRole="button"
                onPress={() => refreshReads(false)}
                style={({pressed}) => [
                  styles.retryButton,
                  styles.macHomeRetryButton,
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.macHomeRetryButtonText}>Retry</Text>
              </FocusPressable>
            )}
          </View>
        )}
      {readOutcomes !== null && !allHomeReadsUnavailable && (
        <View style={styles.macHomeReadStatuses}>
          <OutcomeStatus
            label="Conversations"
            mac
            outcome={readOutcomes.conversations}
          />
          <OutcomeStatus label="Memories" mac outcome={readOutcomes.memories} />
        </View>
      )}
    </View>
  );

  const homeDesktopDeviceAffordance = (
    <DeviceSession
      deviceBusy={deviceBusy}
      deviceScanMessage={deviceScanMessage}
      homeStatus={homeStatus}
      homeStatusColor={homeStatusColor}
      nativeSnapshot={nativeSnapshot}
      onScan={scanForOmi}
      onToggle={toggleDevice}
      variant="affordance"
    />
  );

  const homeDesktopEmptyTitle =
    readsPhase === 'unavailable'
      ? 'Saved data unavailable'
      : homeSearching
      ? 'No results'
      : 'No saved conversations or memories yet.';
  const homeDesktopEmptyCopy =
    readsPhase === 'unavailable' && readOutcomes !== null
      ? desktopRecoveryCopy(readOutcomes.conversations, readOutcomes.memories)
      : homeSearching
      ? 'Filter covers loaded conversations and memories only.'
      : 'Loaded conversations and memories will appear here.';

  const homeDesktopRecovery =
    readsPhase === 'unavailable' ? (
      <HomeRecovery
        copy={homeDesktopEmptyCopy}
        onSignIn={
          homeDesktopEmptyCopy === desktopBackendConfigurationCopy ||
          homeDesktopEmptyCopy === desktopBackendUnauthorizedCopy
            ? () => {
                signInAndRefresh().catch(() => undefined);
              }
            : undefined
        }
        onRetry={() => {
          refreshReads(false).catch(() => undefined);
        }}
        signingIn={signingIn}
        title={homeDesktopEmptyTitle}
      />
    ) : null;
  // A retry from the unavailable state must never flash the resting "none yet"
  // claim: while nothing has loaded, a refresh reads as continued loading.
  const homeTimelineLoading =
    readsPhase === 'initial-loading' ||
    (readsPhase === 'refreshing' && !homeReadsLoadedRef.current);

  const homeDesktop = (
    <HomeSurface footer={homeDesktopDeviceAffordance}>
      <HomeTimeline
        emptyCopy={homeDesktopEmptyCopy}
        emptyTitle={homeDesktopEmptyTitle}
        footer={homeDesktopReadStatus}
        items={homeSpineHasRows ? homeResults : []}
        loading={homeTimelineLoading}
        recovery={homeDesktopRecovery}
      />
    </HomeSurface>
  );

  const firstRunOnboarding = (
    <Onboarding
      onSignIn={() => {
        completeFirstRun().catch(() => undefined);
      }}
      signingIn={signingIn}
    />
  );

  const homeOverview = (
    <ScrollView
      accessibilityLabel="Home overview"
      contentContainerStyle={styles.homeOverviewContent}
      style={styles.homeOverview}>
      <View style={[styles.pendantHero, compact && styles.pendantHeroCompact]}>
        <View
          pointerEvents="none"
          style={[styles.pendantStage, compact && styles.pendantStageCompact]}>
          <OmiMark
            accessibilityLabel="Home pendant"
            height={compact ? 210 : 184}
            size={compact ? 210 : 160}
            source={bundledAssetSource(omiPendant)}
          />
        </View>
        <Text
          style={[styles.pendantName, compact && styles.pendantNameCompact]}>
          Omi
        </Text>
        <View
          accessibilityLabel="Home pendant status"
          style={styles.pendantStatusRow}>
          <View
            style={[
              styles.pendantStatusDot,
              {backgroundColor: homeStatusColor},
            ]}
          />
          <Text
            style={[
              styles.pendantStatus,
              compact && styles.pendantStatusCompact,
            ]}>
            {homeStatus}
          </Text>
        </View>
        {connectedDevice?.battery !== undefined && (
          <View style={styles.pendantBatteryPill}>
            <Text style={styles.pendantBattery}>
              {connectedDevice.battery}% battery
            </Text>
          </View>
        )}
      </View>

      {compact && (
        <>
          <View accessibilityLabel="Home currents" style={styles.homeSection}>
            <View style={styles.homeSectionHeader}>
              <View style={styles.homeSectionAccent} />
              <Text style={[styles.sectionLabel, styles.homeSectionLabel]}>
                Currents
              </Text>
            </View>
            {currentItems.length > 0 ? (
              currentItems.map(item => (
                <ProjectionRow home item={item} key={item.id} />
              ))
            ) : readsPhase === 'initial-loading' ? (
              <Text style={styles.homeHint}>Loading Currents…</Text>
            ) : (
              <Text style={styles.homeHint}>Nothing current right now.</Text>
            )}
          </View>

          <DeviceSession
            bluetoothStatusColor={bluetoothStatusColor}
            deviceBusy={deviceBusy}
            deviceScanMessage={deviceScanMessage}
            nativeSnapshot={nativeSnapshot}
            onScan={scanForOmi}
            onToggle={toggleDevice}
            variant="compact"
          />
        </>
      )}
    </ScrollView>
  );

  const shell = (
    <View
      style={[
        styles.shell,
        compact && styles.shellCompact,
        !compact && !macDesktop && styles.shellWide,
        macDesktop && styles.macShell,
      ]}>
      {macDesktop
        ? onboardingRequired === false
          ? macDesktopNav
          : null
        : !compact
        ? nav
        : null}
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
            !compact && !macDesktop && styles.paneFrameWide,
          ]}>
          {floatingPane && !desktopWorkspace && (
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
              compact && styles.paneCompactSurface,
              desktopWorkspace && styles.desktopPane,
              macDesktop && styles.macPane,
            ]}>
            <Animated.View
              accessibilityLabel={`${route} stage`}
              style={[
                styles.stageMotion,
                {
                  opacity: stageOpacity,
                  transform: [{translateY: stageTranslateY}],
                },
              ]}>
              <View
                style={[
                  styles.stage,
                  compact && styles.stageCompact,
                  desktopWorkspace && styles.desktopStage,
                ]}>
                {onboardingRequired === true ? (
                  firstRunOnboarding
                ) : onboardingRequired !== false ? (
                  <View
                    accessibilityLabel="Session check"
                    style={styles.stage}
                  />
                ) : route === 'Home' && !homeChatOpen ? (
                  desktopWorkspace ? (
                    homeDesktop
                  ) : (
                    <View style={styles.searchHome}>
                      {!compact && (
                        <View style={styles.homeHeading}>
                          <Text
                            accessibilityRole="header"
                            style={styles.homeTitle}>
                            Your Omi, at a glance
                          </Text>
                          <Text style={styles.homeSubtitle}>
                            Device status and the conversations and memories
                            saved for you.
                          </Text>
                        </View>
                      )}
                      {!homeSearching && homeOverview}
                      {homeSearching && (
                        <Animated.View
                          accessibilityLabel="Home search results"
                          style={[
                            styles.homeResults,
                            !compact && styles.homeResultsWide,
                            {opacity: homeResultsOpacity},
                          ]}>
                          <ProjectionList
                            emptyCopy={
                              homeSearching
                                ? 'Clear the search to see saved items.'
                                : 'Start typing to search what is saved.'
                            }
                            emptyTitle={
                              homeSearching ? 'No results' : 'Nothing saved yet'
                            }
                            error={null}
                            footer={
                              <View style={styles.readStatuses}>
                                {readsPhase !== 'ready' && (
                                  <View
                                    style={[
                                      styles.readStatus,
                                      macDesktop && styles.macReadStatus,
                                    ]}>
                                    <Text
                                      style={[
                                        styles.readStatusText,
                                        macDesktop && styles.macReadStatusText,
                                      ]}>
                                      {readsPhase === 'initial-loading'
                                        ? 'Loading saved data…'
                                        : readsPhase === 'refreshing'
                                        ? 'Refreshing saved data…'
                                        : readsPhase ===
                                          'saved-but-refresh-failed'
                                        ? 'Showing saved data. Could not refresh.'
                                        : 'Saved data is unavailable.'}
                                    </Text>
                                    {allHomeReadsUnavailable && (
                                      <Text
                                        style={[
                                          styles.readStatusCopy,
                                          macDesktop &&
                                            styles.macReadStatusText,
                                        ]}>
                                        {readOutcomes === null
                                          ? ''
                                          : desktopRecoveryCopy(
                                              readOutcomes.conversations,
                                              readOutcomes.memories,
                                            )}
                                      </Text>
                                    )}
                                    {(readsPhase ===
                                      'saved-but-refresh-failed' ||
                                      readsPhase === 'unavailable') && (
                                      <FocusPressable
                                        accessibilityLabel="Retry saved data"
                                        accessibilityRole="button"
                                        onPress={() => refreshReads(false)}
                                        style={({pressed}) => [
                                          styles.retryButton,
                                          macDesktop && styles.macRetryButton,
                                          pressed && styles.pressed,
                                        ]}>
                                        <Text
                                          style={[
                                            styles.retryButtonText,
                                            macDesktop &&
                                              styles.macRetryButtonText,
                                          ]}>
                                          Retry
                                        </Text>
                                      </FocusPressable>
                                    )}
                                  </View>
                                )}
                                {readOutcomes !== null &&
                                  !allHomeReadsUnavailable && (
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
                              <View style={styles.homeOverview}>
                                <DeviceSession
                                  deviceBusy={deviceBusy}
                                  deviceScanMessage={deviceScanMessage}
                                  nativeSnapshot={nativeSnapshot}
                                  onScan={scanForOmi}
                                  onToggle={toggleDevice}
                                  variant="overview"
                                />
                                <Text style={styles.sectionLabel}>
                                  Currents
                                </Text>
                              </View>
                            }
                            items={homeResults}
                            loading={readsPhase === 'initial-loading'}
                            suppressEmpty={readsPhase !== 'ready'}
                          />
                        </Animated.View>
                      )}
                      <HomeSearchField
                        compact={compact}
                        desktop={false}
                        inputRef={searchRef}
                        onBlur={() => setSearchFocused(false)}
                        onChangeText={setSearchQuery}
                        onFocus={() => setSearchFocused(true)}
                        onOpenChat={() => setHomeChatOpen(true)}
                        onPressIn={() => setSearchArmed(true)}
                        query={searchQuery}
                        searchArmed={searchArmed}
                        searchFocused={searchFocused}
                      />
                    </View>
                  )
                ) : route === 'Home' ? (
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
                        onPress={() => setHomeChatOpen(false)}
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
                          <Text
                            style={[
                              styles.greeting,
                              macDesktop && styles.macPrimaryText,
                            ]}>
                            I’m ready.
                          </Text>
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
                                onPress={() => {
                                  setDraft(prompt);
                                  composerRef.current?.focus();
                                }}
                                style={({pressed}) => [
                                  styles.promptChip,
                                  compact && styles.promptChipCompact,
                                  pressed && styles.pressed,
                                ]}>
                                <Text style={styles.promptText}>{prompt}</Text>
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
                ) : route === 'Tasks' ? (
                  <TasksPage
                    loading={readsPhase === 'initial-loading'}
                    outcome={routeOutcome}
                  />
                ) : route === 'Connectors' ? (
                  <ConnectorsPage
                    onSignIn={signInAndRefresh}
                    signingIn={signingIn}
                  />
                ) : (
                  <SettingsPage
                    onSignIn={signInAndRefresh}
                    onSignOut={signOutAndRefresh}
                    signingIn={signingIn}
                  />
                )}
              </View>
            </Animated.View>
            {route === 'Home' && homeChatOpen && composer}
          </KeyboardAvoidingView>
        </View>
      </View>
    </View>
  );

  const macDestinationMenu =
    macMenuOpen && onboardingRequired === false ? (
      <Sheet
        onDismiss={() => setMacMenuOpen(false)}
        onSelect={destination => {
          setRoute(destination);
          if (destination === 'Home') {
            setHomeChatOpen(false);
          }
          setMacMenuOpen(false);
        }}
        route={route}
      />
    ) : null;

  return (
    <PageShell
      desktopOverlay={macDestinationMenu}
      macDesktop={macDesktop}
      workspaceMaterial>
      {shell}
    </PageShell>
  );
}

export default App;
