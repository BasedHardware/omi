import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
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
  chatErrorCopy,
  chatHistoryCanReload,
  chatHistoryErrorCopy,
  chatHistoryShouldRefresh,
  chatSessionLost,
  chatHistoryHasOlder,
  chatComposerIsResting,
  chatCancelErrorCopy,
  chatWriteDoorUnavailable,
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
  conversationDayLabel,
  conversationRecapTitle,
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopBackendUnavailableCopy,
  desktopReadsCanRetry,
  desktopRecoveryCopy,
  homeSearchItems,
  visibleDisplayText,
} from '../desktopReadClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import {styles} from '../ui/styles';
import {
  emptyLibraryCopy,
  homeSearchBannerPhase,
  homeSearchPhaseCopy,
  readStatusCopy,
  savedDataEmptyTitle,
  OutcomeStatus,
} from '../ui/ReadStatus';
import {ProjectionList, ProjectionRow} from '../ui/ProjectionList';
import {HomeSearchField} from '../ui/SearchField';
import {Onboarding} from '../ui/Onboarding';
import {PageShell} from '../ui/PageShell';
import {FocusPressable} from '../ui/Pressable';
import {ConversationsPage} from '../pages/Conversations';
import {MemoriesPage} from '../pages/Memories';
import {TasksPage} from '../pages/Tasks';
import {TaskPagination} from '../ui/TaskPagination';
import {ConnectorsPage} from '../pages/Connectors';
import {SettingsPage} from '../pages/Settings';
import {resolveInitialRoute, type Route} from './routes';
import {DeviceSession, homeConnectionStatus} from './DeviceSession';
import {bluetoothSessionColor} from './bluetooth';
import {useDesktopReads} from './useDesktopReads';
import {useTaskMutations} from './useTaskMutations';
import {useOnboarding} from './useOnboarding';
import {useNativeDevices} from './useNativeDevices';
import {useReduceMotion} from './useReduceMotion';
import {omiDotColor} from '../ui/OmiAvatar';
import {OmiMark, bundledAssetSource} from '../ui/OmiMark';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {AppNav} from '../ui/AppNav';
import {Composer} from '../ui/Composer';
import {DesktopApp, DesktopSessionProbe} from '../desktop/DesktopApp';
import {
  MobileAppSurface,
  type MobileProjectionStatus,
  type MobileRoute,
} from '../mobile/MobileAppSurface';

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
  const nativeSessionRequired =
    macDesktop || Platform.OS === 'ios' || Platform.OS === 'android';
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
  const [activeOmiRequestId, setActiveOmiRequestId] = useState<string | null>(
    null,
  );
  const omiRequestRef = useRef<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatWriteDoorClosed, setChatWriteDoorClosed] = useState(false);
  const [chatEpoch, setChatEpoch] = useState(0);
  const chatMutationSeqRef = useRef(0);
  // Monotonic chat session epoch. Each run of the chat-history effect (a gate
  // transition or a backend plane switch) bumps it, so a send or older-page
  // load that started under a retired session can never write transcript
  // state into the session that follows.
  const chatSessionEpochRef = useRef(0);
  const [route, setRoute] = useState<Route>(() =>
    resolveInitialRoute(initialRoute),
  );
  const [requestedConversationId, setRequestedConversationId] = useState<
    string | null
  >(null);
  const consumeRequestedConversation = useCallback(() => {
    setRequestedConversationId(null);
  }, []);
  const [homeChatOpen, setHomeChatOpen] = useState(false);
  const [devicePanelOpen, setDevicePanelOpen] = useState(false);
  // useOnboarding owns the desktop session gate and needs a reads refresh;
  // useDesktopReads must stay idle until that gate is ready. A latest-ref
  // trampoline breaks the cycle without firing reads before the session.
  const refreshReadsRef = useRef<
    (initial: boolean, options?: {ignoreEnabled?: boolean}) => Promise<void>
  >(async () => undefined);
  const refreshReadsViaRef = useCallback(
    (initial: boolean, options?: {ignoreEnabled?: boolean}) =>
      refreshReadsRef.current(initial, options),
    [],
  );
  const {
    authError,
    cancelSignIn,
    completeFirstRun,
    completeSetup,
    completingSetup,
    setupRequired,
    onboardingRequired,
    revalidateSession,
    signInAndRefresh,
    signOutAndRefresh,
    signingIn,
  } = useOnboarding(nativeSessionRequired, refreshReadsViaRef);
  const {
    allHomeReadsUnavailable,
    tasksLoadingMore,
    taskNotice,
    loadMoreTasks,
    tasksPageRetryable,
    readOutcomes,
    reads,
    readsPhase,
    resetReads,
    refreshReads,
    refreshTasks,
    conversationsLoadingMore,
    conversationNotice,
    loadMoreConversations,
    conversationsPageRetryable,
    memoriesLoadingMore,
    memoryNotice,
    loadMoreMemories,
    memoriesPageRetryable,
  } = useDesktopReads({
    enabled: onboardingRequired === false,
  });
  const taskMutations = useTaskMutations({
    enabled: onboardingRequired === false,
    outcome: readOutcomes?.tasks ?? null,
    refreshTasks,
    revalidateSession,
  });
  const taskPagination = (
    <TaskPagination
      hasMore={
        readOutcomes?.tasks.status === 'success' &&
        readOutcomes.tasks.value.page.hasMore &&
        tasksPageRetryable
      }
      busy={
        tasksLoadingMore ||
        readsPhase === 'refreshing' ||
        taskMutations.busyTaskId !== null
      }
      notice={taskNotice}
      onLoadMore={loadMoreTasks}
    />
  );

  useEffect(() => {
    refreshReadsRef.current = refreshReads;
  }, [refreshReads]);
  const reloadWorkspace = useCallback(() => {
    chatSessionEpochRef.current += 1;
    chatMutationSeqRef.current += 1;
    setChatError(null);
    setChatWriteDoorClosed(false);
    setDraft('');
    setMessages([]);
    setOlderChatCursor(null);
    setHasOlderChat(false);
    setChatBusy(false);
    setLoadingOlderChat(false);
    setActiveGenerationId(null);
    stableChatMessageIds.clear();
    animatedChatMessageIds.clear();
    resetReads();
    refreshReads(true).catch(() => undefined);
    setChatEpoch(current => current + 1);
  }, [animatedChatMessageIds, refreshReads, resetReads, stableChatMessageIds]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchArmed, setSearchArmed] = useState(false);
  const [homeSearchFocusNonce, setHomeSearchFocusNonce] = useState(0);
  const [composerFocused, setComposerFocused] = useState(false);
  const {
    deviceBusy,
    deviceScanMessage,
    rememberedDevice,
    rememberedBusy,
    forgetRememberedDevice,
    nativeSnapshot,
    scanForOmi,
    toggleDevice,
  } = useNativeDevices({
    enabled: onboardingRequired === false,
  });
  const searchRef = useRef<TextInput>(null);
  useEffect(() => {
    let active = true;
    chatSessionEpochRef.current += 1;
    const retiredRequest = omiRequestRef.current;
    omiRequestRef.current = null;
    setActiveOmiRequestId(null);
    if (retiredRequest !== null)
      void omiBackend?.cancelOmiChat?.(retiredRequest).catch(() => undefined);
    if (onboardingRequired !== false) {
      // Leaving a ready session drops the previous session's transcript,
      // cursors, and message bookkeeping so nothing leaks across accounts or
      // flashes on the next sign-in. Busy flags reset too: send() refuses to
      // start while chatBusy, so a send that never settled must not brick the
      // next session's composer.
      setChatError(null);
      setChatWriteDoorClosed(false);
      setDraft('');
      setMessages([]);
      setOlderChatCursor(null);
      setHasOlderChat(false);
      setChatBusy(false);
      setLoadingOlderChat(false);
      setActiveGenerationId(null);
      stableChatMessageIds.clear();
      animatedChatMessageIds.clear();
      return () => {
        active = false;
      };
    }
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      return () => undefined;
    }
    // Capture the session this load belongs to. send() bumps mutation so an
    // in-flight setMessages(page) cannot wipe optimistic rows — but that same
    // bump must not discard the history page (cursor + prior messages). Always
    // merge into whatever the session already shows; workspace reload / gate
    // drop clear messages before bumping the epoch.
    const session = chatSessionEpochRef.current;
    const mutation = chatMutationSeqRef.current;
    loadNewestChatHistory(backend)
      .then(page => {
        if (!active || chatSessionEpochRef.current !== session) {
          return;
        }
        page.messages.forEach(message => stableChatMessageIds.add(message.id));
        setMessages(current =>
          reconcileCanonicalChatHistory(current, page.messages),
        );
        setOlderChatCursor(page.olderCursor);
        setHasOlderChat(page.hasOlder);
        setChatError(null);
      })
      .catch(error => {
        if (
          active &&
          chatSessionEpochRef.current === session &&
          mutation === chatMutationSeqRef.current &&
          onboardingRequired === false
        ) {
          setChatError(chatHistoryErrorCopy(error));
          if (chatWriteDoorUnavailable(error)) {
            setChatWriteDoorClosed(true);
          }
          // A 401/unconfigured history load can mean the cloud session died;
          // re-probe it instead of keeping a ready shell on dead credentials.
          if (nativeSessionRequired && chatSessionLost(error)) {
            revalidateSession().catch(() => undefined);
          }
        }
      });
    return () => {
      active = false;
      chatSessionEpochRef.current += 1;
      const requestId = omiRequestRef.current;
      omiRequestRef.current = null;
      if (requestId !== null)
        void backend.cancelOmiChat?.(requestId).catch(() => undefined);
    };
  }, [
    animatedChatMessageIds,
    chatEpoch,
    nativeSessionRequired,
    onboardingRequired,
    revalidateSession,
    stableChatMessageIds,
  ]);

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
    return homeSearchItems(
      reads,
      readOutcomes !== null && readOutcomes.tasks.status === 'success'
        ? readOutcomes.tasks.value.items
        : null,
      searchQuery,
    );
  }, [readOutcomes, reads, searchQuery]);
  const homeSearching = visibleDisplayText(searchQuery) !== '';
  const homeSearchEmptyTitle = savedDataEmptyTitle(
    readOutcomes !== null && readOutcomes.conversations.status === 'success'
      ? readOutcomes.conversations.value.page
      : null,
    readOutcomes !== null && readOutcomes.memories.status === 'success'
      ? readOutcomes.memories.value.page
      : null,
    readOutcomes !== null && readOutcomes.tasks.status === 'success'
      ? readOutcomes.tasks.value.page
      : null,
    homeSearching,
    {
      conversations: conversationNotice === desktopBackendUnavailableCopy,
      memories: memoryNotice === desktopBackendUnavailableCopy,
      tasks: taskNotice === desktopBackendUnavailableCopy,
    },
  );
  // An unavailable Omi cloud read is a single truthful empty state, not a result row. Keeping the
  // results panel content-sized here preserves the upstream two-island hierarchy instead of
  // turning an error into a window-filling modal.
  // A retry from the unavailable state must never flash the resting "none yet"
  // claim: while nothing has loaded, a refresh reads as continued loading.
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

  // A dead cloud session must not keep the product shell up: when every
  // credential-bearing read comes back unauthorized or unconfigured, re-probe
  // the native session and fall back to Welcome if it is really gone.
  useEffect(() => {
    if (
      !nativeSessionRequired ||
      onboardingRequired !== false ||
      readOutcomes === null
    ) {
      return;
    }
    const sessionLost = [
      readOutcomes.conversations,
      readOutcomes.memories,
      readOutcomes.tasks,
    ].some(
      outcome =>
        outcome.status === 'error' &&
        (outcome.error === desktopBackendUnauthorizedCopy ||
          outcome.error === desktopBackendConfigurationCopy),
    );
    if (sessionLost) {
      revalidateSession().catch(() => undefined);
    }
  }, [
    nativeSessionRequired,
    onboardingRequired,
    readOutcomes,
    revalidateSession,
  ]);

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

  const send = async () => {
    const text = draft.trim();
    const backend = omiBackend;
    if (
      backend === undefined ||
      backend === null ||
      visibleDisplayText(draft) === '' ||
      chatBusy ||
      chatWriteDoorClosed
    ) {
      return;
    }
    const session = chatSessionEpochRef.current;
    chatMutationSeqRef.current += 1;
    let admitted = false;
    let requestStarted = false;
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
          admitted = true;
          if (chatSessionEpochRef.current === session) {
            setActiveGenerationId(id);
          }
        },
        localMessage,
        id => {
          if (chatSessionEpochRef.current !== session) return false;
          requestStarted = true;
          omiRequestRef.current = id;
          setActiveOmiRequestId(id);
          return true;
        },
      );
      // A gate transition (sign-out, dead session, plane switch) retired the
      // session this send belonged to: its canonical messages belong to the
      // previous account and must not seed the next session's transcript.
      if (
        chatSessionEpochRef.current !== session ||
        (requestStarted && omiRequestRef.current !== localMessage.id)
      ) {
        return;
      }
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
      if (
        chatSessionEpochRef.current === session &&
        (!requestStarted || omiRequestRef.current === localMessage.id)
      ) {
        if (!admitted && !requestStarted) {
          setMessages(current =>
            current.filter(message => message.id !== localMessage.id),
          );
          setDraft(current => (current === '' ? text : current));
        }
        setChatError(
          admitted || requestStarted
            ? 'Response interrupted. It may still complete.'
            : chatErrorCopy(error),
        );
        if (!admitted && !requestStarted && chatWriteDoorUnavailable(error)) {
          setChatWriteDoorClosed(true);
        }
        if (nativeSessionRequired && chatSessionLost(error)) {
          revalidateSession().catch(() => undefined);
        }
      }
    } finally {
      if (
        chatSessionEpochRef.current === session &&
        (!requestStarted || omiRequestRef.current === localMessage.id)
      ) {
        setActiveGenerationId(null);
        omiRequestRef.current = null;
        setActiveOmiRequestId(null);
        setChatBusy(false);
      }
    }
  };

  const loadOlderMessages = async () => {
    const backend = omiBackend;
    const cursor = olderChatCursor;
    if (
      backend === undefined ||
      backend === null ||
      cursor === null ||
      cursor.length === 0 ||
      loadingOlderChat
    ) {
      return;
    }
    // Capture the session this page belongs to. send() bumps mutation so a
    // replace-style write cannot clobber optimistic rows — but that same bump
    // must not discard a successfully fetched older page (cursor + messages).
    // Merge into the live transcript; only a session epoch change retires it.
    // 410 recovery still respects mutation: a full newest-history replace can
    // wipe a newer send (covered by the stale-recovery test).
    const session = chatSessionEpochRef.current;
    const mutation = chatMutationSeqRef.current;
    setLoadingOlderChat(true);
    setChatError(null);
    try {
      const page = await loadOlderChatHistory(backend, cursor);
      if (chatSessionEpochRef.current !== session) {
        return;
      }
      page.messages.forEach(message => stableChatMessageIds.add(message.id));
      setMessages(current => mergeOlderChatHistory(current, page.messages));
      setOlderChatCursor(page.olderCursor);
      setHasOlderChat(page.hasOlder);
    } catch (error) {
      if (
        chatSessionEpochRef.current !== session ||
        chatMutationSeqRef.current !== mutation
      ) {
        return;
      }
      if (chatHistoryShouldRefresh(error)) {
        try {
          const page = await loadNewestChatHistory(backend);
          if (
            chatSessionEpochRef.current !== session ||
            chatMutationSeqRef.current !== mutation
          ) {
            return;
          }
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
        } catch (recoveryError) {
          if (
            nativeSessionRequired &&
            chatSessionEpochRef.current === session &&
            chatMutationSeqRef.current === mutation &&
            chatSessionLost(recoveryError)
          ) {
            revalidateSession().catch(() => undefined);
          }
        }
      }
      if (chatSessionEpochRef.current === session) {
        setChatError(chatHistoryErrorCopy(error));
        if (chatWriteDoorUnavailable(error)) {
          setChatWriteDoorClosed(true);
        }
        if (!chatHistoryCanReload(error)) {
          setHasOlderChat(false);
        }
        if (nativeSessionRequired && chatSessionLost(error)) {
          revalidateSession().catch(() => undefined);
        }
      }
    } finally {
      if (chatSessionEpochRef.current === session) {
        setLoadingOlderChat(false);
      }
    }
  };

  const stopGeneration = async () => {
    const backend = omiBackend;
    const generationId = activeGenerationId;
    const requestId = omiRequestRef.current;
    if (
      backend === undefined ||
      backend === null ||
      (generationId === null && requestId === null)
    ) {
      return;
    }
    const session = chatSessionEpochRef.current;
    try {
      if (requestId !== null) {
        if (backend.cancelOmiChat === undefined)
          throw new Error('Omi chat cancellation is unavailable');
        await backend.cancelOmiChat(requestId);
        if (
          chatSessionEpochRef.current === session &&
          omiRequestRef.current === requestId
        ) {
          omiRequestRef.current = null;
          setActiveOmiRequestId(null);
          setChatBusy(false);
          setChatError(
            'Response stopped locally. It may still complete on the server.',
          );
        }
      } else if (generationId !== null)
        await cancelChatGeneration(backend, generationId);
    } catch (error) {
      if (chatSessionEpochRef.current === session) {
        setChatError(chatCancelErrorCopy(error));
      }
    }
  };

  const shouldAnimateChatMessage = (id: string) => {
    if (stableChatMessageIds.has(id) || animatedChatMessageIds.has(id)) {
      return false;
    }
    animatedChatMessageIds.add(id);
    return true;
  };

  const olderChatAvailable = chatHistoryHasOlder(hasOlderChat, olderChatCursor);
  const chatResting = chatComposerIsResting(
    messages.length,
    chatBusy,
    hasOlderChat,
    chatError,
  );

  const composer = (
    <Composer
      activeGenerationId={activeGenerationId ?? activeOmiRequestId}
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
      sendUnavailable={chatWriteDoorClosed}
    />
  );

  const {
    connectedDevice,
    label: homeStatus,
    color: homeStatusColor,
  } = homeConnectionStatus(nativeSnapshot);
  const bluetoothStatusColor = bluetoothSessionColor(nativeSnapshot);
  const currentItems = reads.slice(0, 2);

  const firstRunOnboarding = (
    <Onboarding
      setupRequired={setupRequired}
      completingSetup={completingSetup}
      onCompleteSetup={connectDevice => {
        completeSetup()
          .then(completed => {
            if (completed && connectDevice) {
              setRoute('Home');
              setHomeChatOpen(false);
              setDevicePanelOpen(true);
            }
          })
          .catch(() => undefined);
      }}
      onSignOut={
        nativeSessionRequired
          ? () => {
              signOutAndRefresh().catch(() => undefined);
            }
          : undefined
      }
      onCancelSignIn={() => {
        cancelSignIn().catch(() => undefined);
      }}
      error={authError}
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
            rememberedDevice={rememberedDevice}
            rememberedBusy={rememberedBusy}
            onForgetRemembered={forgetRememberedDevice}
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

  if (macDesktop) {
    // Desktop session gate. A Mac that is not fully in — probe unsettled,
    // no cloud session, or first-run onboarding incomplete — never mounts
    // the product shell. The probe holds an empty window (traffic-light
    // spacer only) and a signed-out Mac sees the same Welcome as every other
    // surface, so no signed-in IA leaks before OmiAuth establishes a real
    // session. DesktopApp enforces the same gate for direct mounts.
    if (onboardingRequired !== false) {
      return (
        <PageShell macDesktop workspaceMaterial>
          {onboardingRequired === true ? (
            firstRunOnboarding
          ) : (
            <DesktopSessionProbe />
          )}
        </PageShell>
      );
    }
    return (
      <PageShell macDesktop workspaceMaterial>
        <DesktopApp
          taskPagination={taskPagination}
          {...taskMutations}
          activeGenerationId={activeGenerationId ?? activeOmiRequestId}
          authError={authError}
          chatBusy={chatBusy}
          chatError={chatError}
          chatSendUnavailable={chatWriteDoorClosed}
          deviceContent={
            <DeviceSession
              rememberedDevice={rememberedDevice}
              rememberedBusy={rememberedBusy}
              onForgetRemembered={forgetRememberedDevice}
              bluetoothStatusColor={bluetoothStatusColor}
              deviceBusy={deviceBusy}
              deviceScanMessage={deviceScanMessage}
              nativeSnapshot={nativeSnapshot}
              onScan={scanForOmi}
              onToggle={toggleDevice}
              variant="compact"
            />
          }
          draft={draft}
          hasOlderChat={hasOlderChat}
          olderChatAvailable={olderChatAvailable}
          loadingOlderChat={loadingOlderChat}
          messages={messages}
          onDraftChange={setDraft}
          onLoadOlderChat={() => {
            loadOlderMessages().catch(() => undefined);
          }}
          onRefresh={() => {
            refreshReads(false).catch(() => undefined);
          }}
          onSend={() => {
            send().catch(() => undefined);
          }}
          onStop={() => {
            stopGeneration().catch(() => undefined);
          }}
          onCancelSignIn={() => {
            cancelSignIn().catch(() => undefined);
          }}
          onSignIn={() => {
            signInAndRefresh().catch(() => undefined);
          }}
          onSignOut={() => {
            return signOutAndRefresh();
          }}
          onWorkspaceReload={reloadWorkspace}
          conversationNotice={conversationNotice}
          conversationsLoadingMore={conversationsLoadingMore}
          taskNotice={taskNotice}
          onLoadMoreConversations={
            conversationsPageRetryable
              ? () => {
                  void loadMoreConversations();
                }
              : undefined
          }
          memoryNotice={memoryNotice}
          memoriesLoadingMore={memoriesLoadingMore}
          onLoadMoreMemories={
            memoriesPageRetryable
              ? () => {
                  void loadMoreMemories();
                }
              : undefined
          }
          outcomes={readOutcomes}
          reads={reads}
          readsPhase={readsPhase}
          session={
            onboardingRequired === null
              ? 'probing'
              : onboardingRequired
              ? 'signed-out'
              : 'ready'
          }
          signingIn={signingIn}
        />
      </PageShell>
    );
  }

  if (
    !macDesktop &&
    compact &&
    onboardingRequired === false &&
    !homeChatOpen &&
    (route === 'Home' ||
      route === 'Conversations' ||
      route === 'Tasks' ||
      route === 'Settings' ||
      route === 'Connectors')
  ) {
    const taskItems =
      readOutcomes?.tasks.status === 'success'
        ? readOutcomes.tasks.value.items.map(task => ({
            completed: task.completed,
            dueAt: task.dueAt,
            id: task.id,
            title: task.title,
          }))
        : [];
    const recapNow = Date.now();
    const recapItems =
      readOutcomes?.conversations.status === 'success'
        ? readOutcomes.conversations.value.items.map(item => ({
            dateLabel: conversationDayLabel(
              item.startedAt,
              item.createdAt,
              recapNow,
            ),
            id: item.id,
            starred: item.starred,
            locked: item.locked,
            discarded: item.discarded,
            title: conversationRecapTitle(item),
          }))
        : [];
    const projectionStatus: MobileProjectionStatus =
      readsPhase === 'initial-loading' || readsPhase === 'refreshing'
        ? 'loading'
        : readsPhase === 'unavailable' ||
          readsPhase === 'saved-but-refresh-failed'
        ? 'offline'
        : 'ready';
    const activeMobileRoute: MobileRoute =
      route === 'Tasks'
        ? 'tasks'
        : route === 'Conversations'
        ? 'chat'
        : route === 'Settings'
        ? 'settings'
        : route === 'Connectors'
        ? 'apps'
        : 'home';
    return (
      <MobileAppSurface
        taskPagination={taskPagination}
        {...taskMutations}
        activeRoute={activeMobileRoute}
        conversationContent={
          <ConversationsPage
            onRefresh={() => {
              void refreshReads(false);
            }}
            onLoadMore={
              conversationsPageRetryable
                ? () => {
                    void loadMoreConversations();
                  }
                : undefined
            }
            loadingMore={conversationsLoadingMore}
            notice={conversationNotice}
            outcome={readOutcomes?.conversations ?? null}
            requestedConversationId={requestedConversationId}
            onRequestedConversationConsumed={consumeRequestedConversation}
            loading={
              readsPhase === 'initial-loading' || readsPhase === 'refreshing'
            }
            embedded
          />
        }
        settingsContent={
          <SettingsPage
            onSignIn={signInAndRefresh}
            onSignOut={nativeSessionRequired ? signOutAndRefresh : undefined}
            onWorkspaceReload={reloadWorkspace}
            signingIn={signingIn}
          />
        }
        appsContent={
          <ConnectorsPage onSignIn={signInAndRefresh} signingIn={signingIn} />
        }
        askValue={draft}
        askUnavailable={
          omiBackend === undefined || omiBackend === null || chatWriteDoorClosed
        }
        capture={{
          active: nativeSnapshot?.capture === 'recording',
          waitingForAudio: nativeSnapshot?.audioStatus === 'waiting',
          transcript: '',
        }}
        device={{connected: connectedDevice !== null, label: homeStatus}}
        deviceMessage={devicePanelOpen ? null : deviceScanMessage}
        devicePanel={
          devicePanelOpen ? (
            <DeviceSession
              rememberedDevice={rememberedDevice}
              rememberedBusy={rememberedBusy}
              onForgetRemembered={forgetRememberedDevice}
              bluetoothStatusColor={bluetoothStatusColor}
              deviceBusy={deviceBusy}
              deviceScanMessage={deviceScanMessage}
              nativeSnapshot={nativeSnapshot}
              onScan={scanForOmi}
              onToggle={toggleDevice}
              variant="compact"
            />
          ) : null
        }
        mindMapStatus={
          readOutcomes?.memories.status === 'error' ? 'error' : projectionStatus
        }
        mindMapHasItems={
          readOutcomes?.memories.status === 'success' &&
          readOutcomes.memories.value.items.length > 0
        }
        mindMapEmptyCopy={emptyLibraryCopy(
          'Memories',
          readOutcomes?.memories.status === 'success'
            ? readOutcomes.memories.value.page
            : null,
          false,
          '',
          'No memories yet.',
        )}
        onAskChange={setDraft}
        onAskSubmit={() => {
          if (visibleDisplayText(draft) === '') {
            return;
          }
          setRoute('Home');
          setHomeChatOpen(true);
          send().catch(() => undefined);
        }}
        onExpandMindMap={() => setRoute('Memories')}
        onOpenDevice={() => setDevicePanelOpen(open => !open)}
        onOpenSettings={() => setRoute('Settings')}
        onRouteChange={destination => {
          setHomeChatOpen(false);
          setRoute(
            destination === 'settings'
              ? 'Settings'
              : destination === 'tasks'
              ? 'Tasks'
              : destination === 'apps'
              ? 'Connectors'
              : destination === 'chat'
              ? 'Conversations'
              : 'Home',
          );
        }}
        onViewRecaps={() => {
          setRequestedConversationId(null);
          setRoute('Conversations');
        }}
        onOpenRecap={id => {
          setRequestedConversationId(id);
          setRoute('Conversations');
        }}
        onViewTasks={() => setRoute('Tasks')}
        recapStatus={
          readOutcomes?.conversations.status === 'success'
            ? 'ready'
            : readOutcomes?.conversations.status === 'error'
            ? 'error'
            : projectionStatus
        }
        recaps={recapItems}
        recapEmptyCopy={emptyLibraryCopy(
          'Recaps',
          readOutcomes?.conversations.status === 'success'
            ? readOutcomes.conversations.value.page
            : null,
          false,
          '',
          'No recaps yet',
        )}
        recapCoverageCopy={
          readOutcomes?.conversations.status === 'success'
            ? readStatusCopy(
                'Recaps',
                readOutcomes.conversations.value.page,
                conversationNotice === desktopBackendUnavailableCopy,
              )
            : null
        }
        recapErrorCopy={
          readOutcomes?.conversations.status === 'error'
            ? readOutcomes.conversations.error
            : undefined
        }
        taskEmptyCopy={emptyLibraryCopy(
          'Tasks',
          readOutcomes?.tasks.status === 'success'
            ? readOutcomes.tasks.value.page
            : null,
          false,
          '',
          "Nothing's waiting on you.",
        )}
        taskCoverageCopy={
          readOutcomes?.tasks.status === 'success'
            ? readStatusCopy(
                'Tasks',
                readOutcomes.tasks.value.page,
                taskNotice === desktopBackendUnavailableCopy,
              )
            : null
        }
        taskErrorCopy={
          readOutcomes?.tasks.status === 'error'
            ? readOutcomes.tasks.error
            : undefined
        }
        mindMapErrorCopy={
          readOutcomes?.memories.status === 'error'
            ? readOutcomes.memories.error
            : undefined
        }
        mindMapCoverageCopy={
          readOutcomes?.memories.status === 'success'
            ? readStatusCopy(
                'Memories',
                readOutcomes.memories.value.page,
                memoryNotice === desktopBackendUnavailableCopy,
              )
            : null
        }
        onRefresh={() => {
          void refreshReads(false);
        }}
        tasks={taskItems}
        taskStatus={
          readOutcomes?.tasks.status === 'success'
            ? 'ready'
            : readOutcomes?.tasks.status === 'error'
            ? 'error'
            : projectionStatus
        }
      />
    );
  }

  const shell = (
    <View
      style={[
        styles.shell,
        compact && styles.shellCompact,
        !compact && !macDesktop && styles.shellWide,
        macDesktop && styles.macShell,
      ]}>
      {!compact ? nav : null}
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
                {compact &&
                  route !== 'Home' &&
                  onboardingRequired === false && (
                    <FocusPressable
                      accessibilityLabel="Back to Home"
                      accessibilityRole="button"
                      onPress={() => {
                        setRoute('Home');
                        setHomeChatOpen(false);
                      }}
                      style={[styles.backButton, styles.mobileBackButton]}>
                      <ChevronLeft color="#b0b0b0" size={18} strokeWidth={2} />
                      <Text style={styles.backButtonText}>Home</Text>
                    </FocusPressable>
                  )}
                {onboardingRequired === true ? (
                  firstRunOnboarding
                ) : onboardingRequired !== false ? (
                  <View
                    accessibilityLabel="Session check"
                    style={styles.stage}
                  />
                ) : route === 'Home' && !homeChatOpen ? (
                  <View style={styles.searchHome}>
                    {!compact && (
                      <View style={styles.homeHeading}>
                        <Text
                          accessibilityRole="header"
                          style={styles.homeTitle}>
                          Your Omi, at a glance
                        </Text>
                        <Text style={styles.homeSubtitle}>
                          Device status and the conversations and memories saved
                          for you.
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
                          emptyTitle={homeSearchEmptyTitle}
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
                                    {homeSearchPhaseCopy(
                                      homeSearchBannerPhase(
                                        readsPhase,
                                        allHomeReadsUnavailable,
                                      ),
                                      allHomeReadsUnavailable &&
                                        readOutcomes !== null
                                        ? desktopRecoveryCopy(
                                            readOutcomes.conversations,
                                            readOutcomes.memories,
                                          )
                                        : null,
                                    )}
                                  </Text>
                                  {(readsPhase === 'saved-but-refresh-failed' ||
                                    readsPhase === 'unavailable') &&
                                    desktopReadsCanRetry(readOutcomes) && (
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
                                      continueUnavailable={
                                        conversationNotice ===
                                        desktopBackendUnavailableCopy
                                      }
                                      label="Conversations"
                                      outcome={readOutcomes.conversations}
                                    />
                                    <OutcomeStatus
                                      continueUnavailable={
                                        memoryNotice ===
                                        desktopBackendUnavailableCopy
                                      }
                                      label="Memories"
                                      outcome={readOutcomes.memories}
                                    />
                                  </View>
                                )}
                              {readOutcomes !== null && (
                                <OutcomeStatus
                                  continueUnavailable={
                                    taskNotice === desktopBackendUnavailableCopy
                                  }
                                  label="Tasks"
                                  outcome={readOutcomes.tasks}
                                />
                              )}
                            </View>
                          }
                          header={
                            <View style={styles.homeOverview}>
                              <DeviceSession
                                rememberedDevice={rememberedDevice}
                                rememberedBusy={rememberedBusy}
                                onForgetRemembered={forgetRememberedDevice}
                                deviceBusy={deviceBusy}
                                deviceScanMessage={deviceScanMessage}
                                nativeSnapshot={nativeSnapshot}
                                onScan={scanForOmi}
                                onToggle={toggleDevice}
                                variant="overview"
                              />
                              <Text style={styles.sectionLabel}>Currents</Text>
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
                              chatResting ? styles.home : styles.chatHistory,
                              chatResting
                                ? styles.homeCompact
                                : styles.chatHistoryCompact,
                            ]
                          : chatResting
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
                      {chatResting ? (
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
                            {olderChatAvailable && (
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
                                    : 'Load older messages'}
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
                    onRefresh={() => {
                      void refreshReads(false);
                    }}
                    onLoadMore={
                      conversationsPageRetryable
                        ? () => {
                            void loadMoreConversations();
                          }
                        : undefined
                    }
                    loadingMore={conversationsLoadingMore}
                    notice={conversationNotice}
                    loading={readsPhase === 'initial-loading'}
                    outcome={routeOutcome}
                  />
                ) : route === 'Memories' ? (
                  <MemoriesPage
                    loading={readsPhase === 'initial-loading'}
                    onRefresh={() => {
                      void refreshReads(false);
                    }}
                    outcome={routeOutcome}
                  />
                ) : route === 'Tasks' ? (
                  <TasksPage
                    taskPagination={taskPagination}
                    taskNotice={taskNotice}
                    {...taskMutations}
                    loading={readsPhase === 'initial-loading'}
                    onRefresh={() => {
                      void refreshReads(false);
                    }}
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
                    onWorkspaceReload={reloadWorkspace}
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

  return (
    <PageShell macDesktop={macDesktop} workspaceMaterial>
      {shell}
    </PageShell>
  );
}

export default App;
