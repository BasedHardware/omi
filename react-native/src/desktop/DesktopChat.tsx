import React, {useCallback, useLayoutEffect, useRef, useState} from 'react';
import {Platform, ScrollView, StyleSheet, Text, View} from 'react-native';
import X from 'lucide-react-native/icons/x';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {ChatMessageRow, ChatThinking} from '../ui/ChatTranscript';
import {FocusPressable} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {desktopTokens as token} from './tokens';

type Props = {
  submission: number;
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  loadingHistory?: boolean;
  onLoadOlder: () => void;
  onClose: () => void;
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
  onClose,
}: Props) {
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
          <Text style={styles.title}>What’s on your mind?</Text>
          <Text style={styles.muted}>
            Ask about a conversation, a task, or something you want to remember.
          </Text>
        </View>
      )
    ) : null;
  return (
    <View style={styles.root} accessibilityLabel="Chat with Omi">
      <View style={styles.header}>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Close chat"
          onPress={onClose}
          style={styles.close}>
          <X size={18} color={token.color.ink} />
        </FocusPressable>
      </View>
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
const styles = StyleSheet.create({
  root: {flex: 1, width: '100%', maxWidth: 860, alignSelf: 'center'},
  history: {flex: 1},
  messages: {padding: 20, gap: 20, flexGrow: 1},
  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    padding: 24,
  },
  title: {fontSize: 24, color: token.color.ink, fontWeight: '600'},
  muted: {fontSize: 13, lineHeight: 20, color: token.color.inkMuted},
  earlier: {alignSelf: 'center', padding: 10},
  header: {alignItems: 'flex-end'},
  close: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  error: {color: token.color.ink, paddingHorizontal: 24, fontSize: 13},
});
