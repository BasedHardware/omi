import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import {
  desktopReadsCanRetry,
  type DesktopReadOutcomes,
  type DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {Onboarding} from '../ui/Onboarding';
import {
  desktopNavBarHeight,
  desktopTrafficLightButton,
  desktopTrafficLightRowWidth,
  visibleChatError,
  desktopWindowInset,
  type DesktopSession,
} from './desktopChrome';
import {DesktopChrome, type DesktopRoute} from './DesktopTopChrome';
import {DesktopHome, DesktopReadBanner} from './DesktopHome';
import {AppsPage, LibraryPage, TasksPage} from './DesktopPages';
import type {TaskMutationProps} from '../ui/TaskEditor';
import {DesktopSettings} from './DesktopSettings';
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
  taskPagination?: React.ReactNode;
  deviceContent?: React.ReactNode;
  activeGenerationId: string | null;
  authError: string | null;
  conversationNotice?: string | null;
  conversationsLoadingMore?: boolean;
  onLoadMoreConversations?: () => void;
  taskNotice?: string | null;
  memoryNotice?: string | null;
  memoriesLoadingMore?: boolean;
  onLoadMoreMemories?: () => void;
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
  draft: string;
  messages: ChatMessage[];
  hasOlderChat: boolean;
  olderChatAvailable?: boolean;
  loadingOlderChat: boolean;
  chatBusy: boolean;
  chatError: string | null;
  chatSendUnavailable?: boolean;
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
  activeGenerationId,
  authError,
  conversationNotice = null,
  conversationsLoadingMore = false,
  deviceContent,
  chatBusy,
  chatError,
  chatSendUnavailable = false,
  draft,
  hasOlderChat,
  olderChatAvailable = hasOlderChat,
  loadingOlderChat,
  memoryNotice = null,
  memoriesLoadingMore = false,
  taskNotice = null,
  messages,
  onDraftChange,
  onLoadMoreConversations,
  onLoadMoreMemories,
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
  const [requestedConversationId, setRequestedConversationId] = useState<
    string | null
  >(null);
  const omnibarRef = useRef<TextInput>(null);
  useEffect(() => {
    if (session !== 'ready') {
      setRoute('Home');
      setRequestedConversationId(null);
    }
  }, [session]);
  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setRoute('Home');
      omnibarRef.current?.focus();
    });
    return () => subscription.remove();
  }, []);
  const chatNotice =
    route === 'Home' ? visibleChatError(session, chatError) : null;
  // Session gate. Until OmiAuth reports a real cloud session with onboarding
  // complete, this shell paints no product IA at all: the probe keeps an
  // empty window (traffic-light spacer only) and a signed-out Mac sees the
  // same Welcome as every other surface — never nav pills, an omnibar, Home
  // cards, Settings, or empty-state lists.
  if (session === 'signed-out') {
    return (
      <View accessibilityLabel="Omi desktop" style={styles.root}>
        <Onboarding
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
        activeGenerationId={activeGenerationId}
        chatNotice={chatNotice}
        draft={draft}
        omnibarRef={omnibarRef}
        onDraftChange={onDraftChange}
        onNavigate={setRoute}
        onSend={() => {
          setRoute('Home');
          onSend();
        }}
        onStop={onStop}
        route={route}
        sendUnavailable={chatSendUnavailable}
      />
      {route === 'Conversations' || route === 'Tasks' ? (
        <DesktopReadBanner
          canRetry={desktopReadsCanRetry(outcomes)}
          onRefresh={onRefresh}
          readsPhase={readsPhase}
        />
      ) : null}
      <ShippingStage stageKey={route} variant="page">
        {route === 'Home' ? (
          <DesktopHome
            chatBusy={chatBusy}
            draft={draft}
            hasOlderChat={hasOlderChat}
            olderChatAvailable={olderChatAvailable}
            loadingOlderChat={loadingOlderChat}
            memoryNotice={memoryNotice}
            conversationNotice={conversationNotice}
            taskNotice={taskNotice}
            memoriesLoadingMore={memoriesLoadingMore}
            messages={messages}
            onOpenRewind={() => setRoute('Rewind')}
            onOpenConversation={id => {
              setRequestedConversationId(id);
              setRoute('Conversations');
            }}
            onLoadMoreMemories={onLoadMoreMemories}
            onLoadOlderChat={onLoadOlderChat}
            onRefresh={onRefresh}
            outcomes={outcomes}
            reads={reads}
            readsPhase={readsPhase}
            {...taskMutations}
          />
        ) : route === 'Conversations' ? (
          <LibraryPage
            conversationNotice={conversationNotice}
            conversationsLoadingMore={conversationsLoadingMore}
            onLoadMoreConversations={onLoadMoreConversations}
            onRequestedConversationConsumed={() =>
              setRequestedConversationId(null)
            }
            outcomes={outcomes}
            requestedConversationId={requestedConversationId}
          />
        ) : route === 'Rewind' ? (
          <DesktopRewind capture={capture} captureRevision={captureRevision} />
        ) : route === 'Tasks' ? (
          <TasksPage
            outcomes={outcomes}
            taskNotice={taskNotice}
            {...taskMutations}
          />
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
