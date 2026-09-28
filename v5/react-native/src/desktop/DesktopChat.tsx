import React, {useCallback, useLayoutEffect, useRef, useState} from 'react';
import {Platform, ScrollView, Text, TextInput, View} from 'react-native';
import {MaterialIcon} from '../ui/MaterialIcon';

import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {FocusPressable} from '../ui/Pressable';
import {OmiAvatar} from '../ui/OmiAvatar';
import {ShippingPressable} from './ShippingPressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';

type Props = {
  submission: number;
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  loadingHistory?: boolean;
  onLoadOlder: () => void;
  onSuggest?: (prompt: string) => void;
  draft?: string;
  onDraftChange?: (text: string) => void;
  onSend?: () => void;
  onStop?: () => void;
  canStop?: boolean;
  onClose?: () => void;
  onRetry?: (message: ChatMessage) => void;
};
export function DesktopChat({
  submission,
  messages,
  busy,
  error,
  hasOlder,
  loadingOlder,
  loadingHistory = false,
  onLoadOlder,
  onSuggest,
  draft = '',
  onDraftChange,
  onSend,
  onStop,
  canStop = false,
  onClose,
  onRetry,
}: Props) {
  const styles = useOmiStyles(createStyles);
  const theme = useOmiTheme();
  const list = useRef<ScrollView>(null);
  const composerInput = useRef<TextInput>(null);
  const follow = useRef(true);
  const userScrolling = useRef(false);
  const pointerScrolling = useRef(false);
  const [following, setFollowing] = useState(true);
  const contentHeight = useRef(0);
  const scrollToBottom = useCallback(() => {
    if (follow.current) {
      list.current?.scrollToEnd({animated: false});
    }
  }, []);
  const stopFollowing = useCallback(() => {
    follow.current = false;
    setFollowing(false);
  }, []);
  const jumpToLatest = useCallback(() => {
    follow.current = true;
    setFollowing(true);
    list.current?.scrollToEnd({animated: true});
  }, []);
  const beginUserScroll = useCallback(() => {
    userScrolling.current = true;
    stopFollowing();
  }, [stopFollowing]);
  useLayoutEffect(() => {
    if (Platform.OS !== 'web') {
      return;
    }
    const node = list.current?.getScrollableNode() as
      | (EventTarget & {ownerDocument: EventTarget})
      | undefined;
    if (!node) {
      return;
    }
    const pointerDown = (event: Event) => {
      if (event.target === node) {
        pointerScrolling.current = true;
        beginUserScroll();
      }
    };
    const pointerUp = () => {
      pointerScrolling.current = false;
      userScrolling.current = false;
    };
    const keyDown = (event: Event) => {
      if (
        'key' in event &&
        typeof event.key === 'string' &&
        [
          'ArrowUp',
          'ArrowDown',
          'PageUp',
          'PageDown',
          'Home',
          'End',
          ' ',
        ].includes(event.key)
      ) {
        beginUserScroll();
      }
    };
    node.addEventListener('wheel', beginUserScroll, {passive: true});
    node.addEventListener('touchmove', beginUserScroll, {passive: true});
    node.addEventListener('pointerdown', pointerDown);
    node.addEventListener('keydown', keyDown);
    node.ownerDocument.addEventListener('pointerup', pointerUp);
    node.ownerDocument.addEventListener('pointercancel', pointerUp);
    return () => {
      node.removeEventListener('wheel', beginUserScroll);
      node.removeEventListener('touchmove', beginUserScroll);
      node.removeEventListener('pointerdown', pointerDown);
      node.removeEventListener('keydown', keyDown);
      node.ownerDocument.removeEventListener('pointerup', pointerUp);
      node.ownerDocument.removeEventListener('pointercancel', pointerUp);
    };
  }, [beginUserScroll]);
  useLayoutEffect(() => {
    userScrolling.current = false;
    follow.current = true;
    setFollowing(true);
  }, [submission]);
  useLayoutEffect(() => {
    if (following) {
      scrollToBottom();
    }
  }, [following, submission, scrollToBottom]);
  const reduceMotion = useReduceMotion();
  const empty =
    messages.length === 0 ? (
      loadingHistory ? (
        <View style={styles.empty}>
          <Text style={styles.muted}>Loading conversation…</Text>
        </View>
      ) : error ? (
        <View style={styles.empty}>
          <Text accessibilityRole="header" style={styles.title}>
            Your message wasn’t sent
          </Text>
          <Text style={[styles.muted, styles.emptyCopy]}>
            Your draft is ready below. Press Send to try again.
          </Text>
        </View>
      ) : (
        <View style={styles.empty}>
          <OmiAvatar
            tone="ink"
            inkColor={theme.color.ink}
            size={72}
            motion="arrive"
            reduceMotion={reduceMotion}
          />
          <Text accessibilityRole="header" style={styles.title}>
            What’s on your mind?
          </Text>
          <Text style={[styles.muted, styles.emptyCopy]}>
            Ask about a conversation, a task, or something you want to remember.
          </Text>
          {onSuggest && !busy ? (
            <View style={styles.suggestions}>
              {[
                'Help me think through a decision',
                'Turn these thoughts into a plan',
                'Help me prepare for a conversation',
              ].map(prompt => (
                <ShippingPressable
                  key={prompt}
                  accessibilityRole="button"
                  accessibilityLabel={`Try: ${prompt}`}
                  onPress={() => {
                    onSuggest(prompt);
                    composerInput.current?.focus();
                  }}
                  style={styles.suggestion}>
                  <Text style={styles.suggestionText}>{prompt}</Text>
                  <MaterialIcon
                    name="arrow_outward"
                    size={15}
                    color={theme.color.inkSecondary}
                  />
                </ShippingPressable>
              ))}
            </View>
          ) : null}
        </View>
      )
    ) : null;
  const sendDisabled = !canStop && (busy || !draft.trim());
  return (
    <View style={styles.root} accessibilityLabel="Chat with Omi">
      <View style={styles.history}>
        <ScrollView
          ref={list}
          contentContainerStyle={styles.messages}
          onLayout={() => {
            scrollToBottom();
          }}
          onScrollBeginDrag={beginUserScroll}
          onScrollEndDrag={() => {
            userScrolling.current = false;
          }}
          onMomentumScrollBegin={() => {
            userScrolling.current = true;
          }}
          onMomentumScrollEnd={() => {
            userScrolling.current = false;
          }}
          scrollEventThrottle={16}
          onScroll={event => {
            const {contentOffset, contentSize, layoutMeasurement} =
              event.nativeEvent;
            if (userScrolling.current) {
              const atBottom =
                contentOffset.y + layoutMeasurement.height >=
                contentSize.height - 48;
              follow.current = atBottom;
              setFollowing(atBottom);
              if (Platform.OS === 'web' && !pointerScrolling.current) {
                userScrolling.current = false;
              }
            }
          }}
          onContentSizeChange={(width, height) => {
            contentHeight.current = height;
            scrollToBottom();
          }}>
          {hasOlder ? (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Load earlier messages"
              disabled={loadingOlder}
              onPress={() => {
                userScrolling.current = false;
                stopFollowing();
                onLoadOlder();
              }}
              style={styles.earlier}>
              <Text style={styles.muted}>
                {loadingOlder ? 'Loading earlier…' : 'Load earlier messages'}
              </Text>
            </FocusPressable>
          ) : null}
          {empty}
          {messages.map(item => (
            <ChatMessageRow
              key={item.id}
              message={item}
              compact={false}
              desktop
              animate={false}
              reduceMotion={reduceMotion}
              onRetry={onRetry ? () => onRetry(item) : undefined}
            />
          ))}
          {busy && !messages.some(isStreamingAssistant) ? (
            <ChatThinking reduceMotion={reduceMotion} desktop />
          ) : null}
        </ScrollView>
      </View>
      {!following && messages.length > 0 ? (
        <OmiButton
          label="Jump to Latest"
          compact
          onPress={jumpToLatest}
          style={styles.jump}
        />
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      {onDraftChange && onSend && onStop ? (
        <View style={styles.composerRow}>
          {onClose ? (
            <OmiButton
              label="Activity"
              compact
              variant="plain"
              onPress={onClose}
            />
          ) : null}
          <View style={styles.composer}>
            <TextInput
              ref={composerInput}
              accessibilityLabel="Message Omi"
              placeholder="Ask Omi…"
              placeholderTextColor={theme.color.inkSecondary}
              value={draft}
              onChangeText={onDraftChange}
              onKeyPress={event => {
                if (event.nativeEvent.key === 'Escape') {
                  event.currentTarget.blur();
                }
              }}
              onSubmitEditing={() => {
                if (!busy && draft.trim()) {
                  onSend();
                }
              }}
              style={styles.input}
            />
            {/* Send is an ink circle (stop square while Omi answers), the
                same control as the mobile composer. */}
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel={canStop ? 'Stop' : 'Send'}
              accessibilityState={{disabled: sendDisabled}}
              disabled={sendDisabled}
              onPress={
                canStop
                  ? onStop
                  : () => {
                      if (!busy && draft.trim()) {
                        onSend();
                      }
                    }
              }
              style={state => [
                styles.send,
                sendDisabled && styles.sendDisabled,
                state.pressed && styles.sendPressed,
              ]}>
              <MaterialIcon
                name={canStop ? 'stop' : 'arrow_upward'}
                size={16}
                color={
                  sendDisabled ? theme.color.inkSecondary : theme.color.onInk
                }
              />
            </FocusPressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}
const createStyles = (t: OmiTheme) => ({
  root: {
    flex: 1,
    width: '100%' as const,
    maxWidth: 900,
    alignSelf: 'center' as const,
    backgroundColor: t.color.surface,
    borderColor: t.color.separator,
    borderWidth: 1,
    borderRadius: t.radius.card,
    overflow: 'hidden' as const,
  },
  history: {flex: 1},
  jump: {alignSelf: 'center' as const, marginBottom: t.space.sm},
  composerRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    padding: t.space.md,
    borderTopWidth: 1,
    borderTopColor: t.color.separator,
  },
  composer: {
    flex: 1,
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    minHeight: t.size.control,
    paddingHorizontal: t.space.md,
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: t.color.hairline,
    backgroundColor: t.color.surfaceRaised,
  },
  send: {
    width: 30,
    height: 30,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.ink,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  sendDisabled: {backgroundColor: t.color.fillSelected},
  sendPressed: {opacity: t.motion.pressedOpacity},
  input: {
    ...t.type.body,
    color: t.color.ink,
    flex: 1,
    minWidth: 0,
    paddingVertical: t.space.sm,
  },
  messages: {
    padding: t.space.xl,
    gap: t.space.xl,
    flexGrow: 1,
    maxWidth: t.layout.chatColumn + 2 * t.space.xl,
    width: '100%' as const,
    alignSelf: 'center' as const,
  },
  empty: {
    flex: 1,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
    gap: t.space.md,
    padding: t.space.xxl,
  },
  title: {
    ...t.type.title,
    color: t.color.ink,
    marginTop: t.space.sm,
    textAlign: 'center' as const,
  },
  emptyCopy: {textAlign: 'center' as const, maxWidth: 400},
  suggestions: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    justifyContent: 'center' as const,
    gap: t.space.sm,
    marginTop: t.space.lg,
    alignSelf: 'stretch' as const,
  },
  suggestion: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.sm,
    minHeight: t.size.control,
    paddingHorizontal: t.space.md + 2,
    borderRadius: t.radius.pill,
    borderColor: t.color.hairline,
    borderWidth: 1,
    overflow: 'hidden' as const,
  },
  suggestionText: {
    ...t.type.subhead,
    color: t.color.ink,
  },
  muted: {...t.type.subhead, color: t.color.inkSecondary},
  earlier: {alignSelf: 'center' as const, padding: t.space.sm + 2},
  error: {
    ...t.type.subhead,
    color: t.color.danger,
    backgroundColor: t.color.dangerSurface,
    margin: t.space.md,
    paddingHorizontal: t.space.lg,
    paddingVertical: t.space.md,
    borderRadius: t.radius.row,
  },
});
