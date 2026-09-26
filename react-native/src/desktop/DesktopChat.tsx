import React, {useCallback, useLayoutEffect, useRef, useState} from 'react';
import {Platform, ScrollView, StyleSheet, Text, View} from 'react-native';
import ArrowUpRight from 'lucide-react-native/icons/arrow-up-right';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {FocusPressable} from '../ui/Pressable';
import {OmiAvatar} from '../ui/OmiAvatar';
import {ShippingPressable} from './ShippingPressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

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
}: Props) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: token} = useDesktopTheme();
  const list = useRef<ScrollView>(null);
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
  const fade = useScrollFade();
  const reduceMotion = useReduceMotion();
  const empty =
    messages.length === 0 ? (
      loadingHistory ? (
        <View style={styles.empty}>
          <Text style={styles.muted}>Loading conversation…</Text>
        </View>
      ) : error ? null : (
        <View style={styles.empty}>
          <OmiAvatar
            tone="ink"
            inkColor={token.color.ink}
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
                  onPress={() => onSuggest(prompt)}
                  style={styles.suggestion}>
                  <Text style={styles.suggestionText}>{prompt}</Text>
                  <ArrowUpRight size={15} color={token.color.inkMuted} />
                </ShippingPressable>
              ))}
            </View>
          ) : null}
        </View>
      )
    ) : null;
  return (
    <View style={styles.root} accessibilityLabel="Chat with Omi">
      <ScrollFade visible style={styles.history}>
        <ScrollView
          ref={list}
          contentContainerStyle={styles.messages}
          onLayout={event => {
            fade.onLayout(event);
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
            fade.onScroll(event);
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
            fade.onContentSizeChange(width, height);
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
            />
          ))}
          {busy && !messages.some(isStreamingAssistant) ? (
            <ChatThinking reduceMotion={reduceMotion} desktop />
          ) : null}
        </ScrollView>
      </ScrollFade>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}
const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    root: {flex: 1, width: '100%'},
    history: {flex: 1},
    messages: {padding: 20, gap: 20, flexGrow: 1},
    empty: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      gap: 12,
      padding: 24,
    },
    title: {
      fontSize: 28,
      letterSpacing: -0.6,
      color: token.color.ink,
      fontWeight: '500',
      marginTop: 10,
      textAlign: 'center',
    },
    emptyCopy: {textAlign: 'center', maxWidth: 400},
    suggestions: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
      marginTop: 20,
      alignSelf: 'stretch',
    },
    suggestion: {
      flex: 1,
      flexBasis: 180,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      padding: 16,
      minHeight: 76,
      borderRadius: 14,
      borderColor: token.color.line,
      borderWidth: 1,
      overflow: 'hidden',
    },
    suggestionText: {
      flex: 1,
      fontSize: 12,
      lineHeight: 19,
      color: token.color.inkMuted,
    },
    muted: {fontSize: 13, lineHeight: 20, color: token.color.inkMuted},
    earlier: {alignSelf: 'center', padding: 10},
    error: {
      color: token.color.ink,
      padding: 18,
      fontSize: 13,
      lineHeight: 21,
      borderTopWidth: 1,
      borderColor: token.color.line,
    },
  });
