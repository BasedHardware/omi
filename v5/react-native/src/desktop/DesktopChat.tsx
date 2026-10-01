import React, {useRef} from 'react';
import {Text, TextInput, View} from 'react-native';

import type {ChatMessage} from '../chatClient';
import {ChatComposer} from '../ui/ChatComposer';
import {ChatThread} from '../ui/ChatThread';
import {MaterialIcon} from '../ui/MaterialIcon';
import {useReduceMotion} from '../app/useReduceMotion';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton, OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';

export const desktopChatSuggestions = [
  'Help me think through a decision',
  'Turn these thoughts into a plan',
  'Help me prepare for a conversation',
  'What did I talk about today?',
] as const;

type Props = {
  submission: number;
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  loadingHistory?: boolean;
  /** The history read failed: say so instead of showing an empty chat. */
  historyFailed?: boolean;
  onRetryHistory?: () => void;
  onLoadOlder: () => void;
  onSuggest?: (prompt: string) => void;
  draft?: string;
  onDraftChange?: (text: string) => void;
  onSend?: () => void;
  onStop?: () => void;
  canStop?: boolean;
  onRetry?: (message: ChatMessage) => void;
  /** Optional control inside the composer (Live voice). */
  composerAccessory?: React.ReactNode;
};

/**
 * The desktop Chat destination. It is part of the window, not a sheet: the
 * transcript draws on the same glass as Activity in a centered reading
 * column and scrolls under the chrome; the composer is a capsule anchored
 * to the bottom of that column. With no messages yet, the greeting, the
 * composer and a few suggestions sit together in the middle of the page.
 */
export function DesktopChat({
  submission,
  messages,
  busy,
  error,
  hasOlder,
  loadingOlder,
  loadingHistory = false,
  historyFailed = false,
  onRetryHistory,
  onLoadOlder,
  onSuggest,
  draft = '',
  onDraftChange,
  onSend,
  onStop,
  canStop = false,
  onRetry,
  composerAccessory,
}: Props) {
  const styles = useOmiStyles(createStyles);
  const theme = useOmiTheme();
  const reduceMotion = useReduceMotion();
  const composerInput = useRef<TextInput>(null);
  const historyError = historyFailed && messages.length === 0;
  // Nothing to read yet: greet, and keep the composer with the greeting. A
  // failed first send keeps this layout (the draft stays in the composer).
  const resting =
    messages.length === 0 &&
    !hasOlder &&
    !loadingHistory &&
    !busy &&
    !historyFailed;
  const sendError = error !== null && !historyError ? error : null;
  const canCompose = Boolean(onDraftChange && onSend && onStop);
  const composer =
    canCompose || sendError !== null ? (
      <View key="composer" style={[styles.column, styles.composerColumn]}>
        {sendError !== null ? (
          <View
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            style={styles.notice}>
            <MaterialIcon
              name="info"
              size={theme.size.iconSmall}
              color={theme.color.danger}
            />
            <Text style={styles.noticeText}>{sendError}</Text>
          </View>
        ) : null}
        {onDraftChange && onSend && onStop ? (
          <ChatComposer
            inputRef={composerInput}
            value={draft}
            onChangeText={onDraftChange}
            onSend={onSend}
            onStop={onStop}
            canStop={canStop}
            busy={busy}
            accessory={composerAccessory}
          />
        ) : null}
      </View>
    ) : null;
  if (resting) {
    return (
      <View style={styles.root} accessibilityLabel="Chat with Omi">
        <View key="lead" style={[styles.column, styles.greeting]}>
          <Text accessibilityRole="header" style={styles.title}>
            What’s on your mind?
          </Text>
          <Text style={styles.subtitle}>
            Ask about a conversation, a task, or something you want to remember.
          </Text>
        </View>
        {composer}
        <View key="tail" style={[styles.column, styles.tail]}>
          {onSuggest && error === null ? (
            <View style={styles.suggestions}>
              {desktopChatSuggestions.map(prompt => (
                <OmiButton
                  key={prompt}
                  label={prompt}
                  compact
                  accessibilityLabel={`Try: ${prompt}`}
                  onPress={() => {
                    onSuggest(prompt);
                    composerInput.current?.focus();
                  }}
                />
              ))}
            </View>
          ) : null}
        </View>
      </View>
    );
  }
  return (
    <View style={styles.root} accessibilityLabel="Chat with Omi">
      <ChatThread
        key="lead"
        messages={messages}
        busy={busy}
        desktop
        submission={submission}
        hasOlder={hasOlder}
        loadingOlder={loadingOlder}
        onLoadOlder={onLoadOlder}
        onRetry={onRetry}
        reduceMotion={reduceMotion}
        header={
          messages.length > 0 ? null : loadingHistory ? (
            <OmiPageState kind="loading" label="Loading conversation…" />
          ) : historyError ? (
            <OmiPageState
              kind="error"
              title="Couldn’t Load Chat"
              message={error ?? 'Chat history could not be loaded.'}
              onRetry={onRetryHistory}
            />
          ) : null
        }
      />
      {composer}
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  // No panel: the page is the window's own surface, like Activity.
  root: {flex: 1, minHeight: 0},
  column: {
    width: '100%' as const,
    maxWidth: t.layout.chatColumn + 2 * t.layout.pageGutter.desktop,
    alignSelf: 'center' as const,
    paddingHorizontal: t.layout.pageGutter.desktop,
  },
  composerColumn: {paddingBottom: t.space.lg, gap: t.space.sm},
  greeting: {
    flex: 1,
    justifyContent: 'flex-end' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    paddingBottom: t.space.xxl,
  },
  title: {
    ...t.type.title,
    color: t.color.ink,
    marginTop: t.space.sm,
    textAlign: 'center' as const,
  },
  subtitle: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    textAlign: 'center' as const,
    maxWidth: 420,
  },
  tail: {flex: 1, paddingTop: t.space.xs},
  suggestions: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
  },
  notice: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    paddingHorizontal: t.space.md,
  },
  noticeText: {...t.type.subhead, color: t.color.ink, flex: 1},
});
