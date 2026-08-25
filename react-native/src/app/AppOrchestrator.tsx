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
  Animated,
  Easing,
  Image,
  type ImageSourcePropType,
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
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Brain from 'lucide-react-native/icons/brain';
import ChevronLeft from 'lucide-react-native/icons/chevron-left';
import GanttChartSquare from 'lucide-react-native/icons/square-chart-gantt';
import House from 'lucide-react-native/icons/house';
import ListChecks from 'lucide-react-native/icons/list-checks';
import Mic from 'lucide-react-native/icons/mic';
import PanelLeft from 'lucide-react-native/icons/panel-left';
import PanelLeftClose from 'lucide-react-native/icons/panel-left-close';
import Paperclip from 'lucide-react-native/icons/paperclip';
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
} from '../chatClient';
import {
  browserScanErrorMessage,
  isBluetoothScanAvailable,
  omiBackend,
  omiAuth,
  omiNative,
  type PlatformNativeSnapshot,
} from '../omiNative';
import {
  loadDesktopReads,
  projectionTimestamp,
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopRecoveryCopy,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
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
  {label: 'Connectors', icon: PanelLeftClose},
  {label: 'Settings', icon: PanelLeft},
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
type AppProps = {initialRoute?: string};

function bluetoothStatusLabel(state: string): string {
  switch (state) {
    case 'poweredOn':
      return 'Bluetooth on';
    case 'unauthorized':
      return 'Bluetooth permission needed';
    case 'unsupported':
      return 'Web Bluetooth unavailable';
    case 'available':
      return 'Browser Bluetooth available';
    case 'selected':
      return 'Browser device selected';
    case 'denied':
      return 'Bluetooth permission denied';
    case 'error':
      return 'Bluetooth check failed';
    case 'poweredOff':
      return 'Bluetooth off';
    default:
      return 'Bluetooth status unknown';
  }
}

type ProjectionFilter = 'all' | DesktopReadProjection['kind'];
type ReadsPhase =
  | 'initial-loading'
  | 'refreshing'
  | 'ready'
  | 'saved-but-refresh-failed'
  | 'unavailable';

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

function OmiMark({
  accessibilityLabel = 'Omi',
  height,
  size = 40,
  source = omiLogo,
}: {
  accessibilityLabel?: string;
  height?: number;
  size?: number;
  source?: ImageSourcePropType;
}) {
  const imageHeight = height ?? size;
  return (
    <View
      accessibilityLabel={accessibilityLabel}
      style={
        size === 40 && height === undefined
          ? styles.mark
          : [styles.mark, {height: imageHeight, width: size}]
      }>
      <Image
        resizeMode="contain"
        source={source}
        style={[
          styles.markImage,
          {borderRadius: size / 2, height: imageHeight, width: size},
        ]}
      />
    </View>
  );
}

function bundledAssetSource(asset: string | number): ImageSourcePropType {
  return typeof asset === 'string' ? {uri: asset} : asset;
}

export function omiDotColor(identity: string, index: number): string {
  let hash = 2166136261;
  for (let cursor = 0; cursor < identity.length; cursor += 1) {
    hash ^= identity.charCodeAt(cursor);
    hash = Math.imul(hash, 16777619);
  }
  const hue = (hash + index * 43) >>> 0;
  return `hsl(${hue % 360}, 84%, 66%)`;
}

const omiDotPoses = [
  {ring: {left: 17.5, top: 3.5}, smile: {left: 10, top: 12}},
  {ring: {left: 27.5, top: 7.5}, smile: {left: 26, top: 12}},
  {ring: {left: 31.5, top: 17.5}, smile: {left: 28, top: 23}},
  {ring: {left: 27.5, top: 27.5}, smile: {left: 25, top: 27}},
  {ring: {left: 17.5, top: 31.5}, smile: {left: 21, top: 30}},
  {ring: {left: 7.5, top: 27.5}, smile: {left: 15, top: 30}},
  {ring: {left: 3.5, top: 17.5}, smile: {left: 11, top: 27}},
  {ring: {left: 7.5, top: 7.5}, smile: {left: 8, top: 23}},
] as const;

function OmiAvatar({
  animate = false,
  identity = 'omi',
  reduceMotion = false,
}: {
  animate?: boolean;
  identity?: string;
  reduceMotion?: boolean;
}) {
  const smileProgress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    smileProgress.setValue(0);
    if (!animate || reduceMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(smileProgress, {
          duration: 520,
          easing: Easing.out(Easing.cubic),
          toValue: 1,
          useNativeDriver: true,
        }),
        Animated.timing(smileProgress, {
          duration: 900,
          easing: Easing.out(Easing.cubic),
          toValue: 0,
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [animate, reduceMotion, smileProgress]);

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.chatAvatar}>
      {omiDotPoses.map(({ring, smile}, index) => {
        const translateX = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, smile.left - ring.left],
        });
        const translateY = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, smile.top - ring.top],
        });
        return (
          <Animated.View
            key={index}
            style={[
              styles.chatAvatarDot,
              {backgroundColor: omiDotColor(identity, index)},
              ring,
              {transform: [{translateX}, {translateY}]},
            ]}
          />
        );
      })}
    </View>
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
      <OmiAvatar animate reduceMotion={reduceMotion} />
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
  const [readOutcomes, setReadOutcomes] = useState<DesktopReadOutcomes | null>(
    null,
  );
  const readOutcomesRef = useRef<DesktopReadOutcomes | null>(null);
  // Tracks whether Home ever presented saved rows, independent of the latest
  // refresh outcome, so a failed first load followed by a retry stays truthful.
  const homeReadsLoadedRef = useRef(false);
  const [readsPhase, setReadsPhase] = useState<ReadsPhase>('initial-loading');
  const [signingIn, setSigningIn] = useState(false);
  const [onboardingRequired, setOnboardingRequired] = useState(macDesktop);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchArmed, setSearchArmed] = useState(false);
  const [macMenuOpen, setMacMenuOpen] = useState(false);
  const [homeSearchFocusNonce, setHomeSearchFocusNonce] = useState(0);
  const [composerFocused, setComposerFocused] = useState(false);
  const projectionFilter: ProjectionFilter = 'all';
  const [nativeSnapshot, setNativeSnapshot] =
    useState<PlatformNativeSnapshot | null>(null);
  const [deviceBusy, setDeviceBusy] = useState(false);
  const [deviceScanMessage, setDeviceScanMessage] = useState<string | null>(
    null,
  );
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
    let active = true;
    if (omiNative === undefined || omiNative === null) {
      return () => undefined;
    }
    omiNative
      .getSnapshot()
      .then(snapshot => {
        if (active) {
          setNativeSnapshot(snapshot);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (route === 'Home') {
      Keyboard?.dismiss?.();
    }
  }, [route]);

  const scanForOmi = useCallback(async () => {
    if (omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    setDeviceScanMessage(null);
    try {
      const devices = await omiNative.startScan(8);
      const snapshot = await omiNative.getSnapshot();
      setNativeSnapshot({...snapshot, devices});
    } catch (error) {
      const message = browserScanErrorMessage(error);
      if (message !== null) {
        setDeviceScanMessage(message);
      } else {
        // The native module owns the actual adapter error; preserve its last snapshot.
      }
    } finally {
      setDeviceBusy(false);
    }
  }, []);

  const toggleDevice = useCallback(async (id: string, connected: boolean) => {
    if (omiNative === undefined || omiNative === null) {
      return;
    }
    setDeviceBusy(true);
    try {
      if (connected) {
        await omiNative.disconnectDevice(id);
      } else {
        await omiNative.connectDevice(id);
      }
      setNativeSnapshot(await omiNative.getSnapshot());
    } catch {
      // Connection errors remain native-owned and are reflected on the next snapshot.
    } finally {
      setDeviceBusy(false);
    }
  }, []);

  useEffect(() => {
    if (route === 'Home' && homeChatOpen && shouldFollowChat.current) {
      chatScrollRef.current?.scrollToEnd({animated: !reduceMotion});
    }
  }, [chatBusy, homeChatOpen, messages, reduceMotion, route]);

  const refreshReads = useCallback(async (initial: boolean) => {
    const backend = omiBackend;
    if (backend === undefined || backend === null) {
      const unavailable = {
        status: 'error',
        error: desktopBackendConfigurationCopy,
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
        if (
          next.conversations.status === 'success' ||
          next.memories.status === 'success'
        ) {
          homeReadsLoadedRef.current = true;
        }
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

  useEffect(() => {
    let active = true;
    const auth = omiAuth;
    if (!macDesktop || auth === undefined || auth === null) {
      setOnboardingRequired(false);
      return () => {
        active = false;
      };
    }
    Promise.all([auth.hasCompletedOnboarding(), auth.hasCloudSession()])
      .then(async ([completed, hasSession]) => {
        if (hasSession && !completed) {
          await auth.markOnboardingComplete();
        }
        if (active) {
          setOnboardingRequired(!completed && !hasSession);
        }
      })
      .catch(() => {
        if (active) {
          setOnboardingRequired(true);
        }
      });
    return () => {
      active = false;
    };
  }, [macDesktop]);

  const signInAndRefresh = useCallback(async () => {
    if (omiAuth === undefined || omiAuth === null) {
      return;
    }
    setSigningIn(true);
    try {
      const result = await omiAuth.signIn();
      if (result.signedIn) {
        await omiAuth.markOnboardingComplete();
        await refreshReads(false);
      }
    } finally {
      setSigningIn(false);
    }
  }, [refreshReads]);

  const completeFirstRun = useCallback(async () => {
    if (omiAuth === undefined || omiAuth === null) {
      return;
    }
    setSigningIn(true);
    try {
      const result = await omiAuth.signIn();
      if (result.signedIn) {
        await omiAuth.markOnboardingComplete();
        setOnboardingRequired(false);
        await refreshReads(false);
      }
    } finally {
      setSigningIn(false);
    }
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
    ].sort(
      (left, right) =>
        (projectionTimestamp(right) ?? 0) - (projectionTimestamp(left) ?? 0),
    );
  }, [readOutcomes]);

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

  const allHomeReadsUnavailable =
    readOutcomes !== null &&
    readOutcomes.conversations.status === 'error' &&
    readOutcomes.memories.status === 'error';

  const homeResults = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    return reads.filter(
      item =>
        (projectionFilter === 'all' || item.kind === projectionFilter) &&
        (query === '' ||
          item.searchableText.toLocaleLowerCase().includes(query)),
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
        // Keep first content paint on the JS driver: the native driver can
        // leave this gate at zero during a cold Fabric launch.
        useNativeDriver: false,
      }),
      Animated.timing(stageTranslateY, {
        duration: reduceMotion ? 1 : 180,
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
            onPress={() => {
              setRoute(item.label as Route);
              if (item.label === 'Home') {
                setHomeChatOpen(false);
              }
            }}
          />
        ))}
      </View>
    </Animated.View>
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
          ref={composerRef}
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

  const connectedDevice =
    nativeSnapshot?.devices.find(device => device.connected) ?? null;
  const homeStatus =
    connectedDevice === null
      ? nativeSnapshot === null
        ? 'Checking Bluetooth…'
        : nativeSnapshot.bluetooth === 'poweredOn'
        ? 'Omi disconnected'
        : bluetoothStatusLabel(nativeSnapshot.bluetooth)
      : `Connected · ${
          nativeSnapshot?.capture === 'recording' ? 'Listening' : 'Ready'
        }`;
  const homeStatusColor =
    nativeSnapshot === null
      ? '#b4ad9f'
      : connectedDevice === null
      ? '#d9826f'
      : '#45b79b';
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
    <View
      accessibilityLabel="Home device affordance"
      style={styles.macHomeDeviceAffordance}>
      <View style={styles.macHomeDeviceStatus}>
        <View
          style={[styles.pendantStatusDot, {backgroundColor: homeStatusColor}]}
        />
        <Text style={styles.macHomeDeviceStatusText}>{homeStatus}</Text>
      </View>
      <View style={styles.macHomeDeviceActions}>
        {nativeSnapshot?.devices.map(device => (
          <FocusPressable
            accessibilityLabel={`${
              device.connected ? 'Disconnect' : 'Connect'
            } ${device.name}`}
            accessibilityRole="button"
            disabled={deviceBusy}
            key={device.id}
            onPress={() => toggleDevice(device.id, device.connected)}
            style={({pressed}) => [
              styles.macHomeDeviceChip,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.macHomeDeviceChipText}>
              {device.name} · {device.connected ? 'Connected' : 'Connect'}
            </Text>
          </FocusPressable>
        ))}
        <FocusPressable
          accessibilityLabel="Scan for Omi devices"
          accessibilityRole="button"
          disabled={
            deviceBusy || !isBluetoothScanAvailable(nativeSnapshot?.bluetooth)
          }
          onPress={scanForOmi}
          style={({pressed}) => [
            styles.macHomeDeviceChip,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.macHomeDeviceChipText}>
            {deviceBusy ? 'Scanning…' : 'Devices'}
          </Text>
        </FocusPressable>
      </View>
      {deviceScanMessage !== null && (
        <Text style={styles.macHomeDeviceHint}>{deviceScanMessage}</Text>
      )}
    </View>
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
          <View
            style={[
              styles.pendantAura,
              connectedDevice === null && styles.pendantAuraDisconnected,
            ]}
          />
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
            <View style={styles.pendantBatteryDot} />
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

          <View
            accessibilityLabel="Home devices"
            style={[styles.homeSection, styles.homeDevicesSection]}>
            <View style={styles.homeDeviceCard}>
              <View style={styles.deviceHeader}>
                <View style={styles.homeDeviceHeading}>
                  <View
                    style={[
                      styles.pendantStatusDot,
                      {backgroundColor: bluetoothStatusColor},
                    ]}
                  />
                  <View>
                    <Text
                      style={[styles.sectionLabel, styles.homeSectionLabel]}>
                      Devices
                    </Text>
                    <Text style={[styles.deviceState, styles.homeDeviceState]}>
                      {nativeSnapshot === null
                        ? 'Checking Bluetooth…'
                        : bluetoothStatusLabel(nativeSnapshot.bluetooth)}
                    </Text>
                  </View>
                </View>
                <FocusPressable
                  accessibilityLabel="Scan for Omi devices"
                  accessibilityRole="button"
                  disabled={
                    deviceBusy ||
                    !isBluetoothScanAvailable(nativeSnapshot?.bluetooth)
                  }
                  onPress={scanForOmi}
                  style={({pressed}) => [
                    styles.scanButton,
                    styles.homeScanButton,
                    pressed && styles.pressed,
                  ]}>
                  <Text
                    style={[styles.scanButtonText, styles.homeScanButtonText]}>
                    {deviceBusy ? 'Scanning…' : 'Scan'}
                  </Text>
                </FocusPressable>
              </View>
              {nativeSnapshot?.devices.map(device => (
                <FocusPressable
                  accessibilityLabel={`${
                    device.connected ? 'Disconnect' : 'Connect'
                  } ${device.name}`}
                  accessibilityRole="button"
                  key={device.id}
                  disabled={deviceBusy}
                  onPress={() => toggleDevice(device.id, device.connected)}
                  style={({pressed}) => [
                    styles.deviceRow,
                    styles.homeDeviceRow,
                    pressed && styles.pressed,
                  ]}>
                  <View style={styles.homeDeviceRowLead}>
                    <View
                      style={[
                        styles.homeDeviceRowDot,
                        device.connected && styles.homeDeviceRowDotConnected,
                      ]}
                    />
                    <View>
                      <Text style={styles.deviceName}>{device.name}</Text>
                      <Text style={styles.deviceMeta}>
                        {device.connected ? 'Connected' : `${device.rssi} dBm`}
                      </Text>
                    </View>
                  </View>
                  {device.battery !== undefined && (
                    <Text style={styles.deviceBattery}>{device.battery}%</Text>
                  )}
                </FocusPressable>
              ))}
              {(deviceScanMessage !== null ||
                (nativeSnapshot !== null &&
                  nativeSnapshot.devices.length === 0)) && (
                <Text style={styles.deviceHint}>
                  {deviceScanMessage ??
                    nativeSnapshot?.lastEvent ??
                    'No Omi device was discovered.'}
                </Text>
              )}
            </View>
          </View>
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
                ) : route === 'Home' && !homeChatOpen ? (
                  desktopWorkspace ? (
                    homeDesktop
                  ) : (
                    <View style={styles.searchHome}>
                      {!compact && (
                        <View style={styles.homeHeading}>
                          <Text style={styles.homeEyebrow}>HOME</Text>
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
                                <View style={styles.deviceHeader}>
                                  <View>
                                    <Text style={styles.sectionLabel}>
                                      Devices
                                    </Text>
                                    <Text style={styles.deviceState}>
                                      {nativeSnapshot === null
                                        ? 'Checking Bluetooth…'
                                        : bluetoothStatusLabel(
                                            nativeSnapshot.bluetooth,
                                          )}
                                    </Text>
                                  </View>
                                  <FocusPressable
                                    accessibilityLabel="Scan for Omi devices"
                                    accessibilityRole="button"
                                    disabled={
                                      deviceBusy ||
                                      !isBluetoothScanAvailable(
                                        nativeSnapshot?.bluetooth,
                                      )
                                    }
                                    onPress={scanForOmi}
                                    style={({pressed}) => [
                                      styles.scanButton,
                                      pressed && styles.pressed,
                                    ]}>
                                    <Text style={styles.scanButtonText}>
                                      {deviceBusy ? 'Scanning…' : 'Scan'}
                                    </Text>
                                  </FocusPressable>
                                </View>
                                {nativeSnapshot?.devices.map(device => (
                                  <FocusPressable
                                    accessibilityLabel={`${
                                      device.connected
                                        ? 'Disconnect'
                                        : 'Connect'
                                    } ${device.name}`}
                                    accessibilityRole="button"
                                    key={device.id}
                                    disabled={deviceBusy}
                                    onPress={() =>
                                      toggleDevice(device.id, device.connected)
                                    }
                                    style={({pressed}) => [
                                      styles.deviceRow,
                                      pressed && styles.pressed,
                                    ]}>
                                    <View>
                                      <Text style={styles.deviceName}>
                                        {device.name}
                                      </Text>
                                      <Text style={styles.deviceMeta}>
                                        {device.connected
                                          ? 'Connected'
                                          : `${device.rssi} dBm`}
                                      </Text>
                                    </View>
                                    {device.battery !== undefined && (
                                      <Text style={styles.deviceBattery}>
                                        {device.battery}%
                                      </Text>
                                    )}
                                  </FocusPressable>
                                ))}
                                {(deviceScanMessage !== null ||
                                  (nativeSnapshot !== null &&
                                    nativeSnapshot.devices.length === 0)) && (
                                  <Text style={styles.deviceHint}>
                                    {deviceScanMessage ??
                                      nativeSnapshot?.lastEvent ??
                                      'No Omi device was discovered.'}
                                  </Text>
                                )}
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
                  <ConnectorsPage />
                ) : (
                  <SettingsPage />
                )}
              </View>
            </Animated.View>
            {route === 'Home' && homeChatOpen && composer}
          </KeyboardAvoidingView>
        </View>
      </View>
    </View>
  );

  const macDestinationMenu = macMenuOpen ? (
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
    <PageShell desktopOverlay={macDestinationMenu} macDesktop={macDesktop}>
      {shell}
    </PageShell>
  );
}

export default App;
