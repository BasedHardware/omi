import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
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
import {DesktopHome} from './DesktopHome';
import {AppsPage, LibraryPage, TasksPage} from './DesktopPages';
import {DesktopSettings} from './DesktopSettings';
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

type Props = {
  outcomes: DesktopReadOutcomes | null;
  reads: DesktopReadProjection[];
  readsPhase: ReadsPhase;
  session: DesktopSession;
  signingIn: boolean;
  draft: string;
  messages: ChatMessage[];
  chatBusy: boolean;
  chatError: string | null;
  onRefresh: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onWorkspaceReload?: () => void;
};

export function DesktopApp({
  chatBusy,
  chatError,
  draft,
  messages,
  onDraftChange,
  onRefresh,
  onSend,
  onSignIn,
  onSignOut,
  onWorkspaceReload,
  outcomes,
  reads,
  readsPhase,
  session,
  signingIn,
}: Props) {
  const [route, setRoute] = useState<DesktopRoute>('Home');
  const omnibarRef = useRef<TextInput>(null);
  useEffect(() => {
    const subscription = subscribeDesktopSearchCommand(() => {
      setRoute('Home');
      omnibarRef.current?.focus();
    });
    return () => subscription.remove();
  }, []);
  const chatNotice = visibleChatError(session, chatError);
  // Session gate. Until OmiAuth reports a real cloud session with onboarding
  // complete, this shell paints no product IA at all: the probe keeps an
  // empty window (traffic-light spacer only) and a signed-out Mac sees the
  // same Welcome as every other surface — never nav pills, an omnibar, Home
  // cards, Settings, or empty-state lists.
  if (session === 'signed-out') {
    return (
      <View accessibilityLabel="Omi desktop" style={styles.root}>
        <Onboarding onSignIn={onSignIn} signingIn={signingIn} />
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
        chatNotice={chatNotice}
        draft={draft}
        omnibarRef={omnibarRef}
        onDraftChange={onDraftChange}
        onNavigate={setRoute}
        onSend={onSend}
        route={route}
      />
      <ShippingStage stageKey={route} variant="page">
        {route === 'Home' ? (
          <DesktopHome
            chatBusy={chatBusy}
            draft={draft}
            messages={messages}
            onRefresh={onRefresh}
            outcomes={outcomes}
            reads={reads}
            readsPhase={readsPhase}
          />
        ) : route === 'Conversations' ? (
          <LibraryPage outcomes={outcomes} />
        ) : route === 'Tasks' ? (
          <TasksPage outcomes={outcomes} />
        ) : route === 'Apps' ? (
          <AppsPage session={session} />
        ) : (
          <View style={styles.page}>
            <DesktopSettings
              onSignIn={onSignIn}
              onSignOut={onSignOut}
              onWorkspaceReload={onWorkspaceReload}
              session={session}
              signingIn={signingIn}
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
