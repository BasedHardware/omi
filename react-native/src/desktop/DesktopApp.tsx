import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, TextInput, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {subscribeDesktopSearchCommand} from '../desktopCommands';
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';
import {
  visibleChatError,
  desktopWindowInset,
  type DesktopSession,
} from './desktopChrome';
import {DesktopChrome, type DesktopRoute} from './DesktopTopChrome';
import {DesktopHome, RewindPanel} from './DesktopHome';
import {AppsPage, LibraryPage, TasksPage} from './DesktopPages';
import {DesktopSettings} from './DesktopSettings';
import {ShippingStage} from './ShippingStage';

export type {DesktopSession};

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
            onSignIn={onSignIn}
            outcomes={outcomes}
            reads={reads}
            readsPhase={readsPhase}
            session={session}
            signingIn={signingIn}
          />
        ) : route === 'Library' ? (
          <LibraryPage outcomes={outcomes} />
        ) : route === 'Tasks' ? (
          <TasksPage outcomes={outcomes} />
        ) : route === 'Rewind' ? (
          <View style={styles.page}>
            <RewindPanel />
          </View>
        ) : route === 'Apps' ? (
          <AppsPage />
        ) : (
          <View style={styles.page}>
            <DesktopSettings
              onSignIn={onSignIn}
              onSignOut={onSignOut}
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
  page: {flex: 1},
});
