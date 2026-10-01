import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Platform, StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import type {PostSetupHomeCue} from '../app/usePostSetupHomeCue';
import {DesktopOnboarding} from './DesktopOnboarding';
import {
  desktopOmnibarHeight,
  desktopTrafficLightButton,
  desktopTrafficLightRowWidth,
  visibleChatError,
  desktopWindowInset,
  type ActivityFilterId,
  type DesktopSession,
  type DesktopSettingsPane,
  type TimelineGrouping,
} from './desktopChrome';
import {
  DesktopChrome,
  type DesktopRoute,
  type OmnibarMode,
} from './DesktopTopChrome';
import {PostSetupConfetti, PostSetupOverlay} from './PostSetupOverlay';
import {DesktopThemeProvider, type DesktopThemeName} from './DesktopTheme';
import {DesktopActivity} from './DesktopActivity';
import type {CaptureGroupSummary} from './timeline/UnifiedTimeline';
import {DesktopShellV5} from './DesktopShellV5';
import type {DesktopRouteV5} from './DesktopChromeV5';
import type {TaskMutationProps} from '../ui/TaskEditor';
import {DesktopSettings} from './DesktopSettings';
import type {
  DesktopPreferences,
  DesktopUiVersion,
} from '../desktopSettingsClient';
import {
  loadDesktopPreferences,
  setDesktopPreference,
} from '../desktopSettingsClient';
import {
  parseExploreProgress,
  serializeExploreProgress,
  type ExploreCheck,
} from './exploreChecklist';
import {DesktopChat} from './DesktopChat';
import {DesktopRewind} from './DesktopRewind';
import {useRewindCapture} from '../app/useRewindCapture';
import type {useAmbientAudio} from '../app/useAmbientAudio';
import {ShippingStage} from './ShippingStage';
import {OmiLoadingMark} from '../ui/OmiLoadingMark';
import {useDesktopTheme} from './DesktopTheme';

export type {DesktopSession};

// Window surface. Dark rides the native glass panel behind transparent RN
// content; light paints an opaque paper background — the light native glass
// reads as a milky gray film under translucent RN surfaces.
function DesktopRoot({children}: {children: React.ReactNode}) {
  const {name, tokens} = useDesktopTheme();
  return (
    <View
      accessibilityLabel="Omi desktop"
      style={[
        styles.root,
        name === 'light' && {backgroundColor: tokens.color.dark},
      ]}>
      {children}
    </View>
  );
}

// The probing window keeps traffic-light space and the mark — never an empty
// sheet, and never signed-in chrome, while OmiAuth is still unresolved.
export function DesktopSessionProbe() {
  const {tokens: token} = useDesktopTheme();
  return (
    <View accessibilityLabel="Session check" style={styles.probe}>
      <View pointerEvents="none" style={styles.probeRow}>
        <View pointerEvents="none" style={styles.probeControls} />
      </View>
      <View pointerEvents="none" style={styles.probeMark}>
        <OmiLoadingMark inkColor={token.color.ink} size={80} />
      </View>
    </View>
  );
}

type Props = TaskMutationProps & {
  hostMode?: boolean;
  deviceContent?: React.ReactNode;
  liveVoiceControl?: React.ReactNode;
  ambient?: ReturnType<typeof useAmbientAudio>;
  activeGenerationId: string | null;
  authError: string | null;
  outcomes: DesktopReadOutcomes | null;
  /** Library rows for the selectable v5 pages interface. */
  reads?: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  postSetupHomeCue?: PostSetupHomeCue;
  session: DesktopSession;
  /** Onboarding already finished before; signed-out card says Welcome back. */
  returning?: boolean;
  signingIn: boolean;
  draft: string;
  messages: ChatMessage[];
  hasOlderChat: boolean;
  loadingOlderChat: boolean;
  loadingHistory?: boolean;
  chatBusy: boolean;
  chatError: string | null;
  onRefresh: () => void;
  onSignIn: () => void;
  onCancelSignIn?: () => void;
  onSignOut: () => void | Promise<void>;
  onDraftChange: (value: string) => void;
  onLoadOlderChat: () => void;
  onSend: () => void;
  onStop: () => void;
  onRetryChat?: (message: ChatMessage) => void;
  /** The chat history read failed (not an empty conversation). */
  chatHistoryFailed?: boolean;
  onRetryChatHistory?: () => void;
  onWorkspaceReload?: () => void;
  onPreferencesChange?: (prefs: DesktopPreferences) => void;
  initialAppearance?: DesktopThemeName;
  onAppearanceChange?: (name: DesktopThemeName) => void;
  captureAutoStart?: boolean;
  /** Initial view state for previews and screenshots; users start at Home. */
  initialRoute?: DesktopRoute;
  initialActivityFilter?: ActivityFilterId;
  initialChatOpen?: boolean;
  initialSettingsPane?: DesktopSettingsPane;
  /** Pins the interface revision over the saved preference (previews). */
  initialUiVersion?: DesktopUiVersion;
  initialV5Route?: DesktopRouteV5;
};

export function DesktopApp({
  hostMode = false,
  activeGenerationId,
  authError,
  deviceContent,
  chatBusy,
  chatError,
  ambient,
  draft,
  hasOlderChat,
  loadingOlderChat,
  loadingHistory = false,
  liveVoiceControl,
  messages,
  onDraftChange,
  onLoadOlderChat,
  onRefresh,
  onSend,
  onStop,
  onRetryChat,
  chatHistoryFailed = false,
  onRetryChatHistory,
  onSignIn,
  onCancelSignIn,
  onSignOut,
  onWorkspaceReload,
  onPreferencesChange,
  initialAppearance = 'dark',
  initialRoute = 'Home',
  initialActivityFilter = 'all',
  initialChatOpen = false,
  initialSettingsPane,
  initialUiVersion,
  initialV5Route,
  onAppearanceChange,
  captureAutoStart = false,
  outcomes,
  postSetupHomeCue = null,
  reads = [],
  readsPhase,
  session,
  returning = false,
  signingIn,
  ...taskMutationsRest
}: Props) {
  const [captureRevision, setCaptureRevision] = useState(0);
  const capture = useRewindCapture(
    session === 'ready' && !hostMode,
    () => setCaptureRevision(value => value + 1),
    captureAutoStart,
  );
  const [route, setRoute] = useState<DesktopRoute>(initialRoute);
  const [activityFilter, setActivityFilter] = useState<ActivityFilterId>(
    initialActivityFilter,
  );
  const [groupBy, setGroupBy] = useState<TimelineGrouping>('date');
  // Interface revision: v5 keeps the pages IA selectable from Settings.
  const [uiVersion, setUiVersion] = useState<DesktopUiVersion>(
    initialUiVersion ?? 'v5.1',
  );
  // Saved-v5 users would see one paint of v5.1 chrome before preferences
  // resolve; hold the loading mark until the first read settles.
  const [prefsLoaded, setPrefsLoaded] = useState(false);
  const [focusCaptureId, setFocusCaptureId] = useState<string | null>(null);
  // Chat occupies the stage; the transcript stays in the app state across routes.
  const [chatOpen, setChatOpen] = useState(initialChatOpen);
  const [exploreDone, setExploreDone] = useState<Set<ExploreCheck> | null>(
    null,
  );
  const [guideTarget, setGuideTarget] = useState<
    ActivityFilterId | 'Settings' | null
  >(null);
  const guideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearGuideTimer = useCallback(() => {
    if (guideTimer.current !== null) {
      clearTimeout(guideTimer.current);
      guideTimer.current = null;
    }
  }, []);
  useEffect(() => {
    let cancelled = false;
    loadDesktopPreferences()
      .then(prefs => {
        if (!cancelled) {
          setExploreDone(parseExploreProgress(prefs?.exploreProgress));
          setUiVersion(initialUiVersion ?? prefs?.uiVersion ?? 'v5.1');
          setPrefsLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setExploreDone(new Set());
          setPrefsLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
    // Initial props seed state once; later preference reads own it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => clearGuideTimer, [clearGuideTimer]);

  const markExploreDone = useCallback((next: Set<ExploreCheck>) => {
    setExploreDone(next);
    setDesktopPreference(
      'exploreProgress',
      serializeExploreProgress(next),
    ).catch(() => undefined);
  }, []);
  // Arriving at a surface ticks its checklist item off, once, forever. The
  // Activity page's filters count as arriving at the surface they select.
  useEffect(() => {
    if (exploreDone === null) {
      return;
    }
    const check = chatOpen
      ? ('chat' as ExploreCheck)
      : route === 'Home'
      ? activityFilter === 'conversations'
        ? ('conversations' as ExploreCheck)
        : activityFilter === 'tasks'
        ? ('tasks' as ExploreCheck)
        : activityFilter === 'recall'
        ? ('recall' as ExploreCheck)
        : null
      : route === 'Settings'
      ? ('settings' as ExploreCheck)
      : null;
    if (check === null || exploreDone.has(check)) {
      return;
    }
    markExploreDone(new Set(exploreDone).add(check));
  }, [exploreDone, markExploreDone, route, activityFilter, chatOpen]);
  useEffect(() => {
    if (guideTarget === null) {
      return;
    }
    const arrived =
      guideTarget === 'Settings'
        ? route === 'Settings'
        : route === 'Home' && activityFilter === guideTarget;
    if (arrived) {
      clearGuideTimer();
      setGuideTarget(null);
    }
  }, [activityFilter, clearGuideTimer, guideTarget, route]);
  const startExploreGuide = (check: ExploreCheck) => {
    // v5.1 destinations: the chat overlay, the settings gear, or the filter
    // chip the checklist item selects.
    if (check === 'chat') {
      setMode('Ask');
      setChatOpen(true);
      return;
    }
    if (check === 'settings') {
      if (route === 'Settings') {
        return;
      }
      clearGuideTimer();
      setRoute('Settings');
      setGuideTarget('Settings');
      guideTimer.current = setTimeout(() => setGuideTarget(null), 6000);
      return;
    }
    const target = check as ActivityFilterId;
    if (route === 'Home' && activityFilter === target) {
      return;
    }
    clearGuideTimer();
    setRoute('Home');
    setActivityFilter(target);
    setGuideTarget(target);
    guideTimer.current = setTimeout(() => setGuideTarget(null), 6000);
  };
  const openCaptureFromActivity = (capture: CaptureGroupSummary) => {
    setFocusCaptureId(capture.id);
    setRoute('Rewind');
  };
  const [proveItSeen, setProveItSeen] = useState(false);
  const [confettiFalling, setConfettiFalling] = useState(false);
  const [mode, setMode] = useState<OmnibarMode>('Ask');
  const [recallQuery, setRecallQuery] = useState('');
  // The omnibar doubles as the Settings fuzzy-search field while Settings is
  // open; the query lives here so it survives chrome re-renders and clears on
  // every route change away.
  const [settingsQuery, setSettingsQuery] = useState('');
  const [chatSubmission, setChatSubmission] = useState(0);
  const openChat = () => {
    setMode('Ask');
    setRoute('Home');
    setChatOpen(true);
  };
  useEffect(() => {
    const browserDocument = (
      globalThis as unknown as {
        document?: {
          activeElement?: {blur?: () => void};
          addEventListener: (
            type: string,
            handler: (event: {key: string}) => void,
          ) => void;
          removeEventListener: (
            type: string,
            handler: (event: {key: string}) => void,
          ) => void;
        };
      }
    ).document;
    if (Platform.OS !== 'web' || !browserDocument) {
      return;
    }
    const onEscape = (event: {key: string}) => {
      if (event.key !== 'Escape') {
        return;
      }
      if (chatOpen) {
        browserDocument.activeElement?.blur?.();
      } else if (route !== 'Home') {
        setRoute('Home');
        setMode('Ask');
        setChatOpen(true);
      }
    };
    browserDocument.addEventListener('keydown', onEscape);
    return () => browserDocument.removeEventListener('keydown', onEscape);
  }, [chatOpen, route]);
  useEffect(() => {
    if (mode !== 'Search') {
      return;
    }
    const timer = setTimeout(
      () => setRecallQuery(draft.trim().slice(0, 200)),
      200,
    );
    return () => clearTimeout(timer);
  }, [draft, mode]);
  const navigate = (next: DesktopRoute) => {
    if (next === 'Chat') {
      openChat();
      return;
    }
    setChatOpen(false);
    if (next !== 'Settings') {
      setSettingsQuery('');
    }
    setRoute(next);
    if (next === 'Rewind') {
      setMode('Search');
    } else if (mode === 'Search') {
      setMode('Ask');
    }
  };
  // Chrome filter selection: filters live on the Activity page, so selecting
  // one from any other route returns Home with that filter applied.
  const selectFilter = (next: ActivityFilterId) => {
    setChatOpen(false);
    if (mode === 'Search') {
      setMode('Ask');
    }
    setActivityFilter(next);
    setRoute('Home');
  };
  const omnibarRef = useRef<TextInput>(null);
  const searchFocusPending = useRef(false);
  useEffect(() => {
    if (session !== 'ready') {
      setRoute('Home');
    }
  }, [session]);
  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setMode('Search');
      setChatOpen(false);
      setRoute('Home');
      setActivityFilter('all');
      if (chatOpen) {
        searchFocusPending.current = true;
      } else {
        omnibarRef.current?.focus();
      }
    });
    return () => subscription.remove();
  }, [chatOpen]);
  useEffect(() => {
    if (searchFocusPending.current && !chatOpen && route === 'Home') {
      searchFocusPending.current = false;
      omnibarRef.current?.focus();
    }
  }, [chatOpen, route]);
  const chatNotice = chatOpen ? visibleChatError(session, chatError) : null;
  // Session gate. Until OmiAuth reports a real cloud session with onboarding
  // complete, this shell paints no product IA at all: the probe keeps an
  // empty window (traffic-light spacer only) and a signed-out Mac sees the
  // same Welcome as every other surface — never nav pills, an omnibar, Home
  // cards, Settings, or empty-state lists.
  if (hostMode && session !== 'ready') {
    return null;
  }
  if (session === 'signed-out') {
    return (
      <DesktopThemeProvider
        initialName={initialAppearance}
        onSetName={onAppearanceChange}>
        <DesktopRoot>
          <DesktopOnboarding
            error={authError}
            onSignIn={onSignIn}
            onCancelSignIn={onCancelSignIn}
            returning={returning}
            signingIn={signingIn}
          />
        </DesktopRoot>
      </DesktopThemeProvider>
    );
  }
  if (session === 'probing') {
    return (
      <DesktopThemeProvider
        initialName={initialAppearance}
        onSetName={onAppearanceChange}>
        <DesktopRoot>
          <DesktopSessionProbe />
        </DesktopRoot>
      </DesktopThemeProvider>
    );
  }
  if (!prefsLoaded) {
    return (
      <DesktopThemeProvider
        initialName={initialAppearance}
        onSetName={onAppearanceChange}>
        <DesktopRoot>
          <DesktopSessionProbe />
        </DesktopRoot>
      </DesktopThemeProvider>
    );
  }
  if (uiVersion === 'v5') {
    return (
      <DesktopThemeProvider
        initialName={initialAppearance}
        onSetName={onAppearanceChange}>
        <DesktopRoot>
          <DesktopShellV5
            hostMode={hostMode}
            activeGenerationId={activeGenerationId}
            ambient={ambient}
            capture={capture}
            captureRevision={captureRevision}
            chatBusy={chatBusy}
            chatError={chatError}
            deviceContent={deviceContent}
            draft={draft}
            exploreDone={exploreDone}
            hasOlderChat={hasOlderChat}
            loadingHistory={loadingHistory}
            loadingOlderChat={loadingOlderChat}
            liveVoiceControl={liveVoiceControl}
            messages={messages}
            onDraftChange={onDraftChange}
            onExploreDone={markExploreDone}
            onLoadOlderChat={onLoadOlderChat}
            onPreferencesChange={onPreferencesChange}
            onRefresh={onRefresh}
            onSend={onSend}
            onSignIn={onSignIn}
            onSignOut={onSignOut}
            onStop={onStop}
            onRetryChat={onRetryChat}
            chatHistoryFailed={chatHistoryFailed}
            onRetryChatHistory={onRetryChatHistory}
            onUiVersionChange={setUiVersion}
            onWorkspaceReload={onWorkspaceReload}
            outcomes={outcomes}
            postSetupHomeCue={postSetupHomeCue}
            reads={reads ?? []}
            readsPhase={readsPhase}
            session={session}
            signingIn={signingIn}
            initialRoute={initialV5Route}
            {...taskMutationsRest}
          />
        </DesktopRoot>
      </DesktopThemeProvider>
    );
  }
  return (
    <DesktopThemeProvider
      initialName={initialAppearance}
      onSetName={onAppearanceChange}>
      <DesktopRoot>
        <DesktopChrome
          hostMode={hostMode}
          chatBusy={chatBusy}
          chatActive={chatOpen}
          activeGenerationId={activeGenerationId}
          chatNotice={null}
          draft={draft}
          omnibarRef={omnibarRef}
          onDraftChange={onDraftChange}
          mode={mode}
          onModeChange={next => {
            if (next === 'Search') {
              setMode('Search');
              // Search Recall is the Rewind screen.
              setChatOpen(false);
              setRoute('Rewind');
            } else {
              openChat();
            }
          }}
          onNavigate={navigate}
          filter={activityFilter}
          onFilterChange={selectFilter}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          guideTarget={guideTarget}
          captureActive={capture.capturing}
          captureAvailable={capture.available}
          captureBusy={capture.busy}
          onToggleCapture={
            capture.available
              ? () => {
                  if (capture.capturing) {
                    void capture.stop();
                  } else {
                    void capture.start();
                  }
                }
              : null
          }
          onSend={() => {
            if (mode === 'Ask') {
              setChatSubmission(value => value + 1);
              openChat();
              onSend();
            } else {
              setRecallQuery(draft.trim().slice(0, 200));
              setRoute('Rewind');
            }
          }}
          onStop={onStop}
          route={chatOpen ? 'Chat' : route}
          settingsQuery={settingsQuery}
          onSettingsQueryChange={setSettingsQuery}
        />
        <View style={styles.stage}>
          <ShippingStage stageKey={chatOpen ? 'Chat' : route} variant="page">
            {chatOpen ? (
              <DesktopChat
                submission={chatSubmission}
                messages={messages}
                busy={chatBusy || activeGenerationId !== null}
                draft={draft}
                onDraftChange={onDraftChange}
                onSend={() => {
                  setChatSubmission(value => value + 1);
                  onSend();
                }}
                onStop={onStop}
                canStop={activeGenerationId !== null}
                onRetry={onRetryChat}
                onSuggest={prompt => {
                  onDraftChange(prompt);
                }}
                error={chatNotice}
                hasOlder={hasOlderChat}
                loadingOlder={loadingOlderChat}
                loadingHistory={loadingHistory}
                historyFailed={chatHistoryFailed}
                onRetryHistory={onRetryChatHistory}
                composerAccessory={liveVoiceControl}
                onLoadOlder={onLoadOlderChat}
              />
            ) : route === 'Home' ? (
              <DesktopActivity
                captureRevision={captureRevision}
                exploreDone={exploreDone}
                filter={activityFilter}
                groupBy={groupBy}
                onCapturePress={openCaptureFromActivity}
                onExploreItem={startExploreGuide}
                onRefresh={onRefresh}
                outcomes={outcomes}
                query={mode === 'Search' ? draft : ''}
                readsPhase={readsPhase}
              />
            ) : route === 'Rewind' ? (
              <DesktopRewind
                captureRevision={captureRevision}
                focusCaptureId={focusCaptureId}
                query={recallQuery}
              />
            ) : (
              <View style={styles.page}>
                <DesktopSettings
                  ambient={ambient}
                  capture={capture}
                  deviceContent={deviceContent}
                  query={settingsQuery}
                  onQueryChange={setSettingsQuery}
                  onSignIn={onSignIn}
                  onSignOut={onSignOut}
                  onUiVersionChange={setUiVersion}
                  onWorkspaceReload={onWorkspaceReload}
                  onPreferencesChange={onPreferencesChange}
                  session={session}
                  signingIn={signingIn}
                  softwarePlaneLocked={chatBusy}
                  initialPane={initialSettingsPane}
                />
              </View>
            )}
          </ShippingStage>
        </View>
        {postSetupHomeCue === 'proven' &&
        readsPhase === 'ready' &&
        !proveItSeen ? (
          <PostSetupOverlay
            onContinue={() => setConfettiFalling(true)}
            onClose={() => setProveItSeen(true)}
          />
        ) : null}
        {confettiFalling ? (
          <PostSetupConfetti onDone={() => setConfettiFalling(false)} />
        ) : null}
      </DesktopRoot>
    </DesktopThemeProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'transparent',
    flex: 1,
    gap: 16,
    padding: desktopWindowInset,
  },
  probe: {flex: 1},
  probeRow: {
    flexDirection: 'row',
    height: desktopOmnibarHeight,
  },
  probeMark: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  probeControls: {
    alignSelf: 'center',
    height: desktopTrafficLightButton,
    width: desktopTrafficLightRowWidth,
  },
  page: {flex: 1},
  stage: {flex: 1},
});
