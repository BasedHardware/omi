import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
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
import {AppsPage, LibraryPage, TasksPage} from './DesktopPages';
import type {TaskMutationProps} from '../ui/TaskEditor';
import {DesktopSettings} from './DesktopSettings';
import {DesktopChat} from './DesktopChat';
import {DesktopRewind} from './DesktopRewind';
import {useRewindCapture} from '../app/useRewindCapture';
import {ShippingStage} from './ShippingStage';

export type {DesktopSession};

// The probing window keeps only the chrome row the native traffic lights sit
// in, so an unsettled session probe never reads as a signed-in skeleton.
export function DesktopSessionProbe() {
  return (
    <View accessibilityLabel="Session check" style={styles.probeRow}>
      <View pointerEvents="none" style={styles.probeControls} />
    </View>
  );
}

type Props = TaskMutationProps & {
  onLoadMoreConversations?: () => void;
  conversationsLoadingMore?: boolean;
  conversationNotice?: string | null;
  taskPagination?: React.ReactNode;
  deviceContent?: React.ReactNode;
  activeGenerationId: string | null;
  authError: string | null;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
  draft: string;
  messages: ChatMessage[];
  hasOlderChat: boolean;
  loadingOlderChat: boolean;
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
  draft,
  hasOlderChat,
  loadingOlderChat,
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
  outcomes,
  reads,
  readsPhase,
  session,
  signingIn,
  ...taskMutations
}: Props) {
  const [captureRevision, setCaptureRevision] = useState(0);
  const capture = useRewindCapture(session === 'ready', () =>
    setCaptureRevision(value => value + 1),
  );
  const [route, setRoute] = useState<DesktopRoute>('Home');
  const [mode, setMode] = useState<OmnibarMode>('Ask');
  const [recallQuery, setRecallQuery] = useState('');
  const [chatSubmission, setChatSubmission] = useState(0);
  const beforeChat = useRef<{route: DesktopRoute; mode: OmnibarMode}>({
    route: 'Home',
    mode: 'Ask',
  });
  const openChat = () => {
    if (route !== 'Chat') {
      beforeChat.current = {route, mode};
    }
    setMode('Ask');
    setRoute('Chat');
  };
  const closeChat = () => {
    setRoute(beforeChat.current.route);
    setMode(beforeChat.current.mode);
  };
  useEffect(() => {
    if (mode !== 'Recall') {
      return;
    }
    const timer = setTimeout(
      () => setRecallQuery(draft.trim().slice(0, 200)),
      200,
    );
    return () => clearTimeout(timer);
  }, [draft, mode]);
  const navigate = (next: DesktopRoute) => {
    setRoute(next);
    if (next === 'Rewind') {
      setMode('Recall');
    } else if (mode === 'Recall') {
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
      <View accessibilityLabel="Omi desktop" style={styles.root}>
        <DesktopSessionProbe />
      </View>
    );
  }
  return (
    <View accessibilityLabel="Omi desktop" style={styles.root}>
      <DesktopChrome
        chatBusy={chatBusy}
        capture={capture}
        activeGenerationId={activeGenerationId}
        chatNotice={null}
        draft={draft}
        omnibarRef={omnibarRef}
        onDraftChange={onDraftChange}
        mode={mode}
        onModeChange={next => {
          if (next === 'Ask') {
            openChat();
          } else {
            setMode(next);
            setRoute(next === 'Recall' ? 'Rewind' : 'Home');
          }
        }}
        onNavigate={navigate}
        onSend={() => {
          if (mode === 'Ask') {
            setChatSubmission(value => value + 1);
            openChat();
            onSend();
          } else if (mode === 'Recall') {
            setRecallQuery(draft.trim().slice(0, 200));
            setRoute('Rewind');
          } else {
            setRoute('Home');
          }
        }}
        onStop={onStop}
        route={route}
        backgroundRoute={beforeChat.current.route}
      />
      {route === 'Conversations' || route === 'Tasks' ? (
        <DesktopReadBanner onRefresh={onRefresh} readsPhase={readsPhase} />
      ) : null}
      <ShippingStage stageKey={route} variant="page">
        {route === 'Home' ? (
          <DesktopHome
            chatBusy={chatBusy}
            draft={mode === 'Search' ? draft : ''}
            hasOlderChat={hasOlderChat}
            loadingOlderChat={loadingOlderChat}
            messages={messages}
            onOpenChat={openChat}
            onOpenRewind={() => navigate('Rewind')}
            onOpenTasks={() => setRoute('Tasks')}
            onOpenConversations={() => setRoute('Conversations')}
            onLoadOlderChat={onLoadOlderChat}
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
            onClose={closeChat}
            error={chatNotice}
            hasOlder={hasOlderChat}
            loadingOlder={loadingOlderChat}
            onLoadOlder={onLoadOlderChat}
          />
        ) : route === 'Conversations' ? (
          <LibraryPage
            outcomes={outcomes}
            query={mode === 'Search' ? draft : ''}
            onLoadMore={onLoadMoreConversations}
            loadingMore={conversationsLoadingMore}
            notice={conversationNotice}
          />
        ) : route === 'Rewind' ? (
          <DesktopRewind
            captureRevision={captureRevision}
            query={recallQuery}
          />
        ) : route === 'Tasks' ? (
          <TasksPage outcomes={outcomes} {...taskMutations} />
        ) : route === 'Apps' ? (
          <AppsPage session={session} />
        ) : (
          <View style={styles.page}>
            <DesktopSettings
              capture={capture}
              deviceContent={deviceContent}
              onSignIn={onSignIn}
              onSignOut={onSignOut}
              onWorkspaceReload={onWorkspaceReload}
              session={session}
              signingIn={signingIn}
              softwarePlaneLocked={chatBusy}
            />
          </View>
        )}
      </ShippingStage>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: 'transparent',
    flex: 1,
    gap: 8,
    padding: desktopWindowInset,
  },
  probeRow: {
    flexDirection: 'row',
    height: desktopNavBarHeight,
  },
  probeControls: {
    alignSelf: 'center',
    height: desktopTrafficLightButton,
    width: desktopTrafficLightRowWidth,
  },
  page: {flex: 1},
});
