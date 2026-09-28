import React, {useEffect} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {useReduceMotion} from '../app/useReduceMotion';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {OmiAvatar} from '../ui/OmiAvatar';
import {FocusPressable} from '../ui/Pressable';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {markInk} from './MobileTheme';
import type {OmiTheme} from '../design/tokens';

/** Presentation only. The orchestrator retains requests, history, and scroll-follow state. */
export function MobileChat({
  messages,
  busy,
  error,
  loadingHistory,
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
}: {
  messages: readonly ChatMessage[];
  busy: boolean;
  error: string | null;
  loadingHistory: boolean;
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
}) {
  const reduceMotion = useReduceMotion();
  const theme = useOmiTheme();
  const local = useOmiStyles(createStyles);
  useEffect(() => {
    if (error !== null) {
      scrollRef.current?.scrollToEnd({animated: !reduceMotion});
    }
  }, [error, reduceMotion, scrollRef]);
  const resting =
    messages.length === 0 && !busy && !loadingHistory && error === null;
  return (
    <View style={local.root}>
      <View style={local.header}>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Close chat"
          onPress={onClose}
          style={({pressed}) => [local.back, pressed && local.pressed]}>
          <MaterialIcon
            name="chevron_left"
            color={theme.color.ink}
            size={theme.size.icon + 4}
          />
        </FocusPressable>
        <View style={local.title}>
          <OmiAvatar
            tone="ink"
            size={22}
            inkColor={markInk(theme)}
            motion={busy ? 'breathe' : 'arrive'}
            reduceMotion={reduceMotion}
          />
          <Text accessibilityRole="header" style={local.titleText}>
            Ask Omi
          </Text>
        </View>
        <View style={local.back} />
      </View>
      <ScrollView
        accessibilityLabel="Chat scroll region"
        ref={scrollRef}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyboardShouldPersistTaps="handled"
        style={local.flex}
        contentContainerStyle={local.content}>
        {loadingHistory && (
          <View style={local.notice} accessibilityLabel="Loading chat history">
            <ActivityIndicator color={theme.color.inkSecondary} />
            <Text style={local.copy}>Loading your conversation…</Text>
          </View>
        )}
        {hasOlder && (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Load older messages"
            disabled={loadingOlder}
            onPress={onLoadOlder}
            style={({pressed}) => [local.older, pressed && local.pressed]}>
            <Text style={local.olderText}>
              {loadingOlder ? 'Loading Older…' : 'Load Older Messages'}
            </Text>
          </FocusPressable>
        )}
        {resting && (
          <View style={local.resting}>
            <OmiAvatar
              tone="ink"
              size={56}
              inkColor={markInk(theme)}
              motion="arrive"
              reduceMotion={reduceMotion}
            />
            <Text style={local.restingTitle}>Start With a Thought</Text>
            <Text style={local.restingCopy}>
              Ask about your day, untangle an idea, or find a next step.
            </Text>
            <View style={local.prompts}>
              {prompts.map(prompt => (
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
          </View>
        )}
        {messages.map(message => (
          <ChatMessageRow
            key={message.id}
            message={message}
            compact
            animate={shouldAnimate(message.id)}
            onRetry={onRetry === undefined ? undefined : () => onRetry(message)}
            reduceMotion={reduceMotion}
          />
        ))}
        {busy && !messages.some(isStreamingAssistant) && (
          <ChatThinking reduceMotion={reduceMotion} />
        )}
        {error !== null && (
          <View style={local.error}>
            <MaterialIcon
              name="info"
              size={theme.size.iconSmall}
              color={theme.color.danger}
            />
            <Text accessibilityRole="alert" style={local.errorText}>
              {error}
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {flex: 1, backgroundColor: t.color.canvas},
  flex: {flex: 1},
  pressed: {backgroundColor: t.color.fillPressed},
  header: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    gap: t.space.sm,
    minHeight: 52,
    paddingHorizontal: t.space.sm,
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
  title: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    flexShrink: 1,
  },
  titleText: {...t.type.headline, color: t.color.ink},
  content: {
    flexGrow: 1,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingVertical: t.space.lg,
    gap: t.space.xxl,
  },
  notice: {
    alignItems: 'center' as const,
    gap: t.space.md,
    padding: t.space.xxl,
  },
  copy: {...t.type.subhead, color: t.color.inkSecondary},
  older: {
    alignSelf: 'center' as const,
    minHeight: t.size.hitTarget,
    paddingHorizontal: t.space.lg,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    borderRadius: t.radius.pill,
  },
  olderText: {
    ...t.type.subhead,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  resting: {
    flexGrow: 1,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    gap: t.space.md,
    paddingVertical: t.space.xxl,
  },
  restingTitle: {
    ...t.type.title,
    color: t.color.ink,
    textAlign: 'center' as const,
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
    marginTop: t.space.sm,
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
    alignItems: 'flex-start' as const,
    gap: t.space.sm,
    padding: t.space.md,
    borderRadius: t.radius.row,
    backgroundColor: t.color.dangerSurface,
  },
  errorText: {...t.type.subhead, color: t.color.ink, flex: 1},
});
