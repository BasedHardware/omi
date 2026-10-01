import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import type {ChatMessage} from '../chatClient';
import {useReduceMotion} from '../app/useReduceMotion';
import {ChatThread} from '../ui/ChatThread';
import {FocusPressable} from '../ui/Pressable';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';

/**
 * The phone chat page, pushed over the tab it came from: Back, a title, the
 * shared transcript, and (outside this component) the composer attached to
 * the bottom edge above the keyboard. Presentation only: the orchestrator
 * owns requests, history and the draft.
 */
export function MobileChat({
  messages,
  busy,
  error,
  loadingHistory,
  historyFailed = false,
  onRetryHistory,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  onClose,
  onRetry,
  onUsePrompt,
  prompts,
  scrollRef,
  onScroll,
  shouldAnimate,
  onJumpLatest,
}: {
  messages: readonly ChatMessage[];
  busy: boolean;
  error: string | null;
  loadingHistory: boolean;
  /** The history read failed: say so instead of showing an empty chat. */
  historyFailed?: boolean;
  onRetryHistory?: () => void;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
  onClose: () => void;
  onRetry?: (message: ChatMessage) => void;
  onUsePrompt: (prompt: string) => void;
  prompts: readonly string[];
  scrollRef: React.RefObject<ScrollView | null>;
  onScroll: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
  shouldAnimate: (id: string) => boolean;
  onJumpLatest?: () => void;
}) {
  const reduceMotion = useReduceMotion();
  const theme = useOmiTheme();
  const local = useOmiStyles(createStyles);
  const historyError = historyFailed && messages.length === 0;
  const resting =
    messages.length === 0 &&
    !hasOlder &&
    !busy &&
    !loadingHistory &&
    !historyFailed;
  const sendError = error !== null && !historyError ? error : null;
  return (
    <View style={local.root}>
      <View style={local.header}>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Back from chat"
          onPress={onClose}
          style={({pressed}) => [local.back, pressed && local.pressed]}>
          <MaterialIcon
            name="chevron_left"
            color={theme.color.ink}
            size={theme.size.icon + 6}
          />
        </FocusPressable>
        <Text
          accessibilityRole="header"
          numberOfLines={1}
          style={local.titleText}>
          Ask Omi
        </Text>
        <View style={local.back} />
      </View>
      {resting ? (
        // Scrolls so the greeting and prompts stay reachable above the
        // keyboard on small phones.
        <ScrollView
          accessibilityLabel="Chat transcript"
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          contentContainerStyle={local.resting}>
          <Text accessibilityRole="header" style={local.restingTitle}>
            What’s on your mind?
          </Text>
          <Text style={local.restingCopy}>
            Ask about your day, untangle an idea, or find a next step.
          </Text>
          <View style={local.prompts}>
            {(error === null ? prompts : []).map(prompt => (
              <FocusPressable
                key={prompt}
                accessibilityRole="button"
                accessibilityLabel={`Try: ${prompt}`}
                onPress={() => onUsePrompt(prompt)}
                style={({pressed}) => [
                  local.prompt,
                  pressed && local.promptPressed,
                ]}>
                <Text style={local.promptText}>{prompt}</Text>
              </FocusPressable>
            ))}
          </View>
        </ScrollView>
      ) : (
        <ChatThread
          messages={messages}
          busy={busy}
          desktop={false}
          hasOlder={hasOlder}
          loadingOlder={loadingOlder}
          onLoadOlder={onLoadOlder}
          onRetry={onRetry}
          shouldAnimate={shouldAnimate}
          scrollRef={scrollRef}
          onScroll={onScroll}
          onJumpLatest={onJumpLatest}
          reduceMotion={reduceMotion}
          header={
            messages.length > 0 ? null : loadingHistory ? (
              <OmiPageState kind="loading" label="Loading your conversation…" />
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
      )}
      {sendError !== null ? (
        <View
          accessibilityRole="alert"
          accessibilityLiveRegion="polite"
          style={local.error}>
          <MaterialIcon
            name="info"
            size={theme.size.iconSmall}
            color={theme.color.danger}
          />
          <Text style={local.errorText}>{sendError}</Text>
        </View>
      ) : null}
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {flex: 1, backgroundColor: t.color.canvas},
  pressed: {backgroundColor: t.color.fillPressed},
  header: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    gap: t.space.sm,
    minHeight: 52,
    paddingHorizontal: t.space.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: t.color.separator,
  },
  back: {
    width: t.size.hitTarget,
    height: t.size.hitTarget,
    borderRadius: t.radius.pill,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  titleText: {
    ...t.type.headline,
    color: t.color.ink,
    flexShrink: 1,
    textAlign: 'center' as const,
  },
  resting: {
    flexGrow: 1,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingBottom: t.space.xxl,
  },
  restingTitle: {
    ...t.type.title,
    color: t.color.ink,
    textAlign: 'center' as const,
    marginTop: t.space.sm,
  },
  restingCopy: {
    ...t.type.subhead,
    textAlign: 'center' as const,
    color: t.color.inkSecondary,
    maxWidth: 300,
  },
  prompts: {
    alignSelf: 'stretch' as const,
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
    marginTop: t.space.lg,
  },
  prompt: {
    minHeight: t.size.hitTarget,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.lg,
    borderRadius: t.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.hairline,
  },
  promptPressed: {backgroundColor: t.color.fillPressed},
  promptText: {...t.type.subhead, color: t.color.ink},
  error: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    marginHorizontal: t.layout.pageGutter.mobile,
    marginBottom: t.space.sm,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.sm,
    borderRadius: t.radius.row,
    backgroundColor: t.color.dangerSurface,
  },
  errorText: {...t.type.subhead, color: t.color.ink, flex: 1},
});
