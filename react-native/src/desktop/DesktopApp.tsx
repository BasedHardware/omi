import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
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
  desktopNavBarHeight,
  desktopTrafficLightButton,
  desktopTrafficLightRowWidth,
  visibleChatError,
  desktopWindowInset,
  type DesktopSession,
} from './desktopChrome';
import {
  DesktopChrome,
  type DesktopRoute,
  type OmnibarMode,
} from './DesktopTopChrome';
import {DesktopHome, DesktopReadBanner} from './DesktopHome';
import {PostSetupConfetti, PostSetupOverlay} from './PostSetupOverlay';
import {DesktopThemeProvider, type DesktopThemeName} from './DesktopTheme';
import {UnifiedTimeline} from './timeline/UnifiedTimeline';
import {unifiedTimelineEnabled} from './timeline/flag';
import {LibraryPage, TasksPage} from './DesktopPages';
import type {TaskMutationProps} from '../ui/TaskEditor';
import {DesktopSettings} from './DesktopSettings';
import type {DesktopPreferences} from '../desktopSettingsClient';
import {DesktopChat} from './DesktopChat';
import {DesktopRewind} from './DesktopRewind';
import {useRewindCapture} from '../app/useRewindCapture';
import type {useAmbientAudio} from '../app/useAmbientAudio';
import {ShippingStage} from './ShippingStage';
import {OmiLoadingMark} from '../ui/OmiLoadingMark';
import {useDesktopTheme} from './DesktopTheme';

export type {DesktopSession};

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
  onLoadMoreConversations?: () => void;
  conversationsLoadingMore?: boolean;
  conversationNotice?: string | null;
  taskPagination?: React.ReactNode;
  deviceContent?: React.ReactNode;
  liveVoiceControl?: React.ReactNode;
  ambient?: ReturnType<typeof useAmbientAudio>;
  activeGenerationId: string | null;
  authError: string | null;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  postSetupHomeCue?: PostSetupHomeCue;
  session: DesktopSession;
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
};

export function DesktopApp({
  onLoadMoreConversations,
  conversationsLoadingMore = false,
  conversationNotice = null,
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
  onAppearanceChange,
  captureAutoStart = false,
  outcomes,
  postSetupHomeCue = null,
  reads,
  readsPhase,
  session,
  signingIn,
  ...taskMutations
}: Props) {
  const [captureRevision, setCaptureRevision] = useState(0);
  const capture = useRewindCapture(
    session === 'ready',
    () => setCaptureRevision(value => value + 1),
    captureAutoStart,
  );
  const [route, setRoute] = useState<DesktopRoute>('Home');
  const [proveItSeen, setProveItSeen] = useState(false);
  const [confettiFalling, setConfettiFalling] = useState(false);
  const [mode, setMode] = useState<OmnibarMode>('Ask');
  const [recallQuery, setRecallQuery] = useState('');
  const [chatSubmission, setChatSubmission] = useState(0);
  const openChat = () => {
    setMode('Ask');
    setRoute('Chat');
  };
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
    setRoute(next);
    if (next === 'Rewind') {
      setMode('Search');
    } else if (mode === 'Search') {
      setMode('Ask');
    }
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
      setRoute('Home');
      omnibarRef.current?.focus();
    });
    return () => subscription.remove();
  }, []);
  const chatNotice =
    route === 'Chat' ? visibleChatError(session, chatError) : null;
  // Session gate. Until OmiAuth reports a real cloud session with onboarding
  // complete, this shell paints no product IA at all: the probe keeps an
  // empty window (traffic-light spacer only) and a signed-out Mac sees the
  // same Welcome as every other surface — never nav pills, an omnibar, Home
  // cards, Settings, or empty-state lists.
  if (session === 'signed-out') {
    return (
      <View accessibilityLabel="Omi desktop" style={styles.root}>
        <DesktopOnboarding
          error={authError}
          onSignIn={onSignIn}
          onCancelSignIn={onCancelSignIn}
          signingIn={signingIn}
        />
      </View>
    );
  }
  if (session === 'probing') {
    return (
      <DesktopThemeProvider
        initialName={initialAppearance}
        onSetName={onAppearanceChange}>
        <View accessibilityLabel="Omi desktop" style={styles.root}>
          <DesktopSessionProbe />
        </View>
      </DesktopThemeProvider>
    );
  }
  return (
    <DesktopThemeProvider
      initialName={initialAppearance}
      onSetName={onAppearanceChange}>
      <View accessibilityLabel="Omi desktop" style={styles.root}>
        <DesktopChrome
          chatBusy={chatBusy}
          capture={capture}
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
          route={route}
        />
        {route === 'Conversations' || route === 'Tasks' ? (
          <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
        ) : null}
        <ShippingStage stageKey={route} variant="page">
          {route === 'Home' ? (
            <DesktopHome
              draft={mode === 'Search' ? draft : ''}
              onOpenRewind={() => navigate('Rewind')}
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
          ) : route === 'Conversations' ? (
            unifiedTimelineEnabled ? (
              <UnifiedTimeline
                outcomes={outcomes}
                query={mode === 'Search' ? draft : ''}
                loading={readsPhase === 'initial-loading'}
              />
            ) : (
              <LibraryPage
                outcomes={outcomes}
                query={mode === 'Search' ? draft : ''}
                onLoadMore={onLoadMoreConversations}
                loadingMore={conversationsLoadingMore}
                notice={conversationNotice}
              />
            )
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
    height: desktopNavBarHeight,
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
});
