import React, {useCallback, useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, TextInput, View} from 'react-native';
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
import {useDesktopTheme, useDesktopStyleSheets} from './DesktopTheme';
import type {DesktopTokens} from './tokens';
import {FocusPressable} from '../ui/Pressable';
import {MaterialIcon} from '../ui/MaterialIcon';
import {useOmiStyles} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';

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
  const [uiVersion, setUiVersion] =
    useState<DesktopUiVersion>(initialUiVersion ?? 'v5.1');
  // Saved-v5 users would see one paint of v5.1 chrome before preferences
  // resolve; hold the loading mark until the first read settles.
  const [prefsLoaded, setPrefsLoaded] = useState(false);
  const [focusCaptureId, setFocusCaptureId] = useState<string | null>(null);
  // Chat is an overlay, not a page: small asks answer inline under the
  // omnibar and the full transcript opens here on demand.
  const [chatOpen, setChatOpen] = useState(initialChatOpen);
  const [inlineAnswerOpen, setInlineAnswerOpen] = useState(false);
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
  const [chatSubmission, setChatSubmission] = useState(0);
  const openChat = () => {
    setMode('Ask');
    setInlineAnswerOpen(false);
    setChatOpen(true);
  };
  const closeChat = () => setChatOpen(false);
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
      omnibarRef.current?.focus();
    });
    return () => subscription.remove();
  }, []);
  const chatNotice =
    chatOpen || inlineAnswerOpen ? visibleChatError(session, chatError) : null;
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
          activeGenerationId={activeGenerationId}
          chatNotice={null}
          draft={draft}
          omnibarRef={omnibarRef}
          onDraftChange={onDraftChange}
          liveControl={chatOpen ? liveVoiceControl : undefined}
          mode={mode}
          onModeChange={next => {
            setMode(next);
            if (next === 'Search') {
              // Search Recall is the Rewind screen: leave any overlay behind.
              setChatOpen(false);
              setInlineAnswerOpen(false);
              setRoute('Rewind');
            } else if (route === 'Rewind') {
              setRoute('Home');
              setActivityFilter('all');
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
              // Small asks answer inline under the omnibar, like the mobile
              // app; the full transcript is one click away.
              setInlineAnswerOpen(true);
              onSend();
            } else {
              setRecallQuery(draft.trim().slice(0, 200));
              setRoute('Rewind');
            }
          }}
          onStop={onStop}
          route={route}
          inlineCard={
            inlineAnswerOpen && !chatOpen ? (
              <InlineAskCard
                busy={chatBusy || activeGenerationId !== null}
                messages={messages}
                notice={chatNotice}
                onClose={() => setInlineAnswerOpen(false)}
                onOpenChat={openChat}
              />
            ) : undefined
          }
        />
        <View style={styles.stage}>
          <ShippingStage stageKey={route} variant="page">
            {route === 'Home' ? (
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
          {chatOpen ? (
            <ChatOverlay onClose={closeChat}>
              <DesktopChat
                submission={chatSubmission}
                messages={messages}
                busy={chatBusy || activeGenerationId !== null}
                onSuggest={prompt => {
                  setMode('Ask');
                  onDraftChange(prompt);
                  omnibarRef.current?.focus();
                }}
                error={chatNotice}
                hasOlder={hasOlderChat}
                loadingOlder={loadingOlderChat}
                loadingHistory={loadingHistory}
                onLoadOlder={onLoadOlderChat}
              />
            </ChatOverlay>
          ) : null}
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

// Small ask answers pinned under the omnibar: the trailing exchange with a
// way into the full transcript, like the mobile app's inline bubble.
function InlineAskCard({
  busy,
  messages,
  notice,
  onClose,
  onOpenChat,
}: {
  busy: boolean;
  messages: ChatMessage[];
  notice: string | null;
  onClose: () => void;
  onOpenChat: () => void;
}) {
  const styles = useDesktopStyleSheets(createInlineStyles);
  const {tokens: token} = useDesktopTheme();
  // The exchange the omnibar just started: the last human turn plus whatever
  // the assistant has answered so far.
  const lastAsk = [...messages].reduce(
    (index, message, position) =>
      message.sender === 'human' ? position : index,
    -1,
  );
  const ask = lastAsk >= 0 ? messages[lastAsk] : undefined;
  const answer = messages
    .slice(lastAsk + 1)
    .find(message => message.sender === 'ai');
  return (
    <View accessibilityLabel="Inline chat answer" style={styles.card}>
      <View style={styles.cardHead}>
        <Text style={styles.cardTitle}>Omi</Text>
        <FocusPressable
          accessibilityLabel="Dismiss answer"
          accessibilityRole="button"
          onPress={onClose}
          style={({pressed}) => [styles.close, pressed && styles.pressed]}>
          <MaterialIcon name="close" size={14} color={token.color.inkMuted} />
        </FocusPressable>
      </View>
      {ask !== undefined && ask.text.trim() !== '' ? (
        <Text style={styles.cardAsk} numberOfLines={2}>
          {ask.text.trim()}
        </Text>
      ) : null}
      {notice !== null ? (
        <Text style={styles.cardNotice}>{notice}</Text>
      ) : answer !== undefined && answer.text.trim() !== '' ? (
        <Text style={styles.cardText} numberOfLines={4}>
          {answer.text.trim()}
        </Text>
      ) : (
        <View style={styles.thinking}>
          <OmiLoadingMark inkColor={token.color.ink} size={18} />
          <Text style={styles.cardText}>
            {busy ? 'Thinking…' : 'No answer yet.'}
          </Text>
        </View>
      )}
      <FocusPressable
        accessibilityLabel="Open chat"
        accessibilityRole="button"
        onPress={onOpenChat}
        style={({pressed}) => [styles.openChat, pressed && styles.pressed]}>
        <Text style={styles.openChatText}>Open chat</Text>
      </FocusPressable>
    </View>
  );
}

const createInlineStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    card: {
      backgroundColor: token.color.dark,
      borderColor: token.color.lineStrong,
      borderRadius: 14,
      borderWidth: 1,
      gap: 8,
      padding: 12,
    },
    cardHead: {
      alignItems: 'center',
      flexDirection: 'row',
      justifyContent: 'space-between',
    },
    cardTitle: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 11,
      fontWeight: '600',
      letterSpacing: 0.4,
      textTransform: 'uppercase',
    },
    close: {
      alignItems: 'center',
      borderRadius: 8,
      height: 22,
      justifyContent: 'center',
      width: 22,
    },
    thinking: {
      alignItems: 'center',
      flexDirection: 'row',
      gap: 8,
    },
    cardText: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: token.type.body,
      lineHeight: 20,
    },
    cardAsk: {
      color: token.color.inkMuted,
      fontFamily: token.font,
      fontSize: 13,
      lineHeight: 18,
    },
    cardNotice: {
      color: token.color.red,
      fontFamily: token.font,
      fontSize: 13,
      lineHeight: 18,
    },
    openChat: {
      alignSelf: 'flex-start',
      backgroundColor: token.color.glassSelected,
      borderRadius: 10,
      paddingHorizontal: 12,
      paddingVertical: 6,
    },
    openChatText: {
      color: token.color.ink,
      fontFamily: token.font,
      fontSize: 12,
      fontWeight: '600',
    },
    pressed: {opacity: 0.7},
  });

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
  // Stage wrapper: the page and the chat overlay share this region, so the
  // overlay never covers the omnibar that feeds chat.
  stage: {flex: 1},
});

// The chat overlay renders inside DesktopThemeProvider (DesktopApp itself
// mounts the provider), so its surface and scrim follow the appearance: a
// light surface with dark ink in light, the dark surface in dark.
function ChatOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  const overlayStyles = useOmiStyles(createOverlayStyles);
  return (
    <View accessibilityLabel="Chat overlay" style={overlayStyles.chatOverlay}>
      <FocusPressable
        accessibilityLabel="Close chat"
        accessibilityRole="button"
        onPress={onClose}
        style={overlayStyles.chatScrim}
      />
      <View style={overlayStyles.chatPanel}>{children}</View>
    </View>
  );
}

const createOverlayStyles = (t: OmiTheme) => ({
  chatOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 20,
  },
  chatScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: t.color.scrim,
  },
  chatPanel: {
    alignSelf: 'center' as const,
    backgroundColor: t.color.surface,
    borderColor: t.color.separator,
    borderRadius: t.radius.card,
    borderWidth: 1,
    flex: 1,
    marginVertical: t.space.xs,
    maxHeight: 720,
    maxWidth: t.layout.chatColumn + 2 * t.space.page,
    overflow: 'hidden' as const,
    width: '100%' as const,
  },
});
