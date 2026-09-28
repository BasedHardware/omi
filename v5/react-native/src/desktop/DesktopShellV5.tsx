import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Platform, StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import type {DesktopReadOutcomes} from '../desktopReadClient';
import type {DesktopReadProjection} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import type {PostSetupHomeCue} from '../app/usePostSetupHomeCue';
import type {useAmbientAudio} from '../app/useAmbientAudio';
import type {useRewindCapture} from '../app/useRewindCapture';
import {visibleChatError, type DesktopSession} from './desktopChrome';
import {
  DesktopChromeV5,
  type DesktopRouteV5,
  type OmnibarModeV5,
} from './DesktopChromeV5';
import {DesktopHome, DesktopReadBanner} from './DesktopHome';
import {LibraryPage, TasksPage} from './DesktopPages';
import {DesktopChat} from './DesktopChat';
import {DesktopRewind} from './DesktopRewind';
import {DesktopSettings} from './DesktopSettings';
import {ShippingStage} from './ShippingStage';
import {PostSetupConfetti, PostSetupOverlay} from './PostSetupOverlay';
import type {ExploreCheck} from './exploreChecklist';
import type {TaskMutationProps} from '../ui/TaskEditor';
import type {DesktopPreferences} from '../desktopSettingsClient';

// The v5 pages IA: a rail of destinations (Home / Chat / Conversations /
// Recall / Tasks), the omnibar on the second row, and one page per rail id.
// Kept selectable from Settings → General so the previous major interface
// revision ships inside the same app.
type ShellProps = TaskMutationProps & {
  hostMode?: boolean;
  activeGenerationId: string | null;
  ambient?: ReturnType<typeof useAmbientAudio>;
  capture: ReturnType<typeof useRewindCapture>;
  captureRevision: number;
  chatBusy: boolean;
  chatError: string | null;
  deviceContent?: React.ReactNode;
  draft: string;
  exploreDone: Set<ExploreCheck> | null;
  hasOlderChat: boolean;
  loadingHistory?: boolean;
  loadingOlderChat: boolean;
  liveVoiceControl?: React.ReactNode;
  messages: ChatMessage[];
  onDraftChange: (value: string) => void;
  onExploreDone: (done: Set<ExploreCheck>) => void;
  onLoadOlderChat: () => void;
  onPreferencesChange?: (prefs: DesktopPreferences) => void;
  onRefresh: () => void;
  onSend: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onStop: () => void;
  onRetryChat?: (message: ChatMessage) => void;
  onUiVersionChange?: (version: 'v5' | 'v5.1') => void;
  onWorkspaceReload?: () => void;
  outcomes: DesktopReadOutcomes | null;
  postSetupHomeCue?: PostSetupHomeCue;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
  /** Initial rail route for previews and screenshots; users start at Home. */
  initialRoute?: DesktopRouteV5;
};

// v5 checklist destinations are rail routes, not filters.
const EXPLORE_ROUTE_V5: Record<ExploreCheck, DesktopRouteV5> = {
  recall: 'Rewind',
  chat: 'Chat',
  conversations: 'Conversations',
  tasks: 'Tasks',
  settings: 'Settings',
};

export function DesktopShellV5({
  hostMode = false,
  activeGenerationId,
  ambient,
  capture,
  captureRevision,
  chatBusy,
  chatError,
  deviceContent,
  draft,
  exploreDone,
  hasOlderChat,
  loadingHistory = false,
  loadingOlderChat,
  liveVoiceControl,
  messages,
  onDraftChange,
  onExploreDone,
  onLoadOlderChat,
  onPreferencesChange,
  onRefresh,
  onSend,
  onSignIn,
  onSignOut,
  onStop,
  onRetryChat,
  onUiVersionChange,
  onWorkspaceReload,
  outcomes,
  postSetupHomeCue = null,
  reads,
  readsPhase,
  session,
  signingIn,
  initialRoute = 'Home',
  ...taskMutations
}: ShellProps) {
  const [route, setRoute] = useState<DesktopRouteV5>(initialRoute);
  const [guideTarget, setGuideTarget] = useState<DesktopRouteV5 | null>(null);
  const guideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearGuideTimer = useCallback(() => {
    if (guideTimer.current !== null) {
      clearTimeout(guideTimer.current);
      guideTimer.current = null;
    }
  }, []);
  useEffect(() => clearGuideTimer, [clearGuideTimer]);
  // Arriving at a surface ticks its checklist item off, once, forever.
  useEffect(() => {
    if (exploreDone === null) {
      return;
    }
    const check = (Object.keys(EXPLORE_ROUTE_V5) as ExploreCheck[]).find(
      id => EXPLORE_ROUTE_V5[id] === route,
    );
    if (check === undefined || exploreDone.has(check)) {
      return;
    }
    const next = new Set(exploreDone);
    next.add(check);
    onExploreDone(next);
  }, [exploreDone, onExploreDone, route]);
  useEffect(() => {
    if (guideTarget !== null && route === guideTarget) {
      clearGuideTimer();
      setGuideTarget(null);
    }
  }, [clearGuideTimer, guideTarget, route]);
  const startExploreGuide = (check: ExploreCheck) => {
    const target = EXPLORE_ROUTE_V5[check];
    if (target === undefined || route === target) {
      return;
    }
    clearGuideTimer();
    setGuideTarget(target);
    guideTimer.current = setTimeout(() => setGuideTarget(null), 6000);
  };
  const [proveItSeen, setProveItSeen] = useState(false);
  const [confettiFalling, setConfettiFalling] = useState(false);
  const [mode, setMode] = useState<OmnibarModeV5>('Ask');
  const [recallQuery, setRecallQuery] = useState('');
  const [chatSubmission, setChatSubmission] = useState(0);
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
  const openChat = () => {
    setMode('Ask');
    setRoute('Chat');
  };
  const navigate = (next: DesktopRouteV5) => {
    if (next === 'Chat') {
      openChat();
      return;
    }
    setRoute(next);
    if (next === 'Rewind') {
      setMode('Search');
    } else if (mode === 'Search') {
      setMode('Ask');
    }
  };
  const omnibarRef = useRef<TextInput>(null);
  const searchFocusPending = useRef(false);
  useEffect(() => {
    if (route !== 'Chat' && searchFocusPending.current) {
      searchFocusPending.current = false;
      omnibarRef.current?.focus();
    }
  }, [route]);
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
      if (route === 'Chat') {
        browserDocument.activeElement?.blur?.();
      } else if (route !== 'Home') {
        openChat();
      }
    };
    browserDocument.addEventListener('keydown', onEscape);
    return () => browserDocument.removeEventListener('keydown', onEscape);
  }, [route]);
  useEffect(() => {
    if (session !== 'ready') {
      setRoute('Home');
    }
  }, [session]);
  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setMode('Search');
      setRoute('Home');
      if (route === 'Chat') {
        searchFocusPending.current = true;
      } else {
        omnibarRef.current?.focus();
      }
    });
    return () => subscription.remove();
  }, [route]);
  const chatNotice =
    route === 'Chat' ? visibleChatError(session, chatError) : null;
  return (
    <View style={styles.root}>
      <DesktopChromeV5
        hostMode={hostMode}
        chatBusy={chatBusy}
        activeGenerationId={activeGenerationId}
        chatNotice={null}
        draft={draft}
        omnibarRef={omnibarRef}
        onDraftChange={onDraftChange}
        liveControl={route === 'Chat' ? liveVoiceControl : undefined}
        mode={mode}
        onModeChange={next => {
          setMode(next);
          if (next === 'Search') {
            setRoute('Rewind');
          } else if (route === 'Rewind') {
            setRoute('Home');
          }
        }}
        onNavigate={navigate}
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
            if (route !== 'Chat') {
              openChat();
            }
            onSend();
          } else {
            setRecallQuery(draft.trim().slice(0, 200));
            setRoute('Rewind');
          }
        }}
        onStop={onStop}
        route={route}
      />
      {route === 'Conversations' || route === 'Tasks' ? (
        <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      ) : null}
      <ShippingStage stageKey={route} variant="page">
        {route === 'Home' ? (
          <DesktopHome
            draft={mode === 'Search' ? draft : ''}
            exploreDone={exploreDone}
            onExploreGuide={startExploreGuide}
            onOpenTasks={() => setRoute('Tasks')}
            onOpenConversations={() => setRoute('Conversations')}
            onRefresh={onRefresh}
            outcomes={outcomes}
            reads={reads}
            readsPhase={readsPhase}
          />
        ) : route === 'Chat' ? (
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
            onClose={() => navigate('Home')}
            onRetry={onRetryChat}
            onSuggest={prompt => {
              setMode('Ask');
              onDraftChange(prompt);
            }}
            error={chatNotice}
            hasOlder={hasOlderChat}
            loadingOlder={loadingOlderChat}
            loadingHistory={loadingHistory}
            onLoadOlder={onLoadOlderChat}
          />
        ) : route === 'Conversations' ? (
          <LibraryPage
            outcomes={outcomes}
            query={mode === 'Search' ? draft : ''}
            onRefresh={onRefresh}
          />
        ) : route === 'Rewind' ? (
          <DesktopRewind
            captureRevision={captureRevision}
            query={recallQuery}
          />
        ) : route === 'Tasks' ? (
          <TasksPage outcomes={outcomes} {...taskMutations} />
        ) : (
          <View style={styles.page}>
            <DesktopSettings
              ambient={ambient}
              capture={capture}
              deviceContent={deviceContent}
              onSignIn={onSignIn}
              onSignOut={onSignOut}
              onUiVersionChange={onUiVersionChange}
              onWorkspaceReload={onWorkspaceReload}
              onPreferencesChange={onPreferencesChange}
              session={session}
              signingIn={signingIn}
              softwarePlaneLocked={chatBusy}
            />
          </View>
        )}
      </ShippingStage>
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
    </View>
  );
}

const styles = StyleSheet.create({
  // DesktopRoot (in DesktopApp) owns the window inset padding; this shell
  // only stacks its chrome and page.
  root: {
    backgroundColor: 'transparent',
    flex: 1,
    gap: 16,
  },
  page: {flex: 1},
});
