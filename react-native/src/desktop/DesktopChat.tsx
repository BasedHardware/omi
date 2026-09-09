import React, {useCallback, useLayoutEffect, useRef} from 'react';
import {FlatList, StyleSheet, Text, View} from 'react-native';
import X from 'lucide-react-native/icons/x';
import type {ChatMessage} from '../chatClient';
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
  onLoadOlder,
  onClose,
}: Props) {
  const list = useRef<FlatList<ChatMessage>>(null);
  const follow = useRef(true);
  useLayoutEffect(() => {
    follow.current = true;
    list.current?.scrollToEnd({animated: false});
  }, [submission]);
  const fade = useScrollFade();
  const reduceMotion = useReduceMotion();
  const renderItem = useCallback(
    ({item}: {item: ChatMessage}) => (
      <ChatMessageRow
        message={item}
        compact={false}
        desktop
        animate={false}
        reduceMotion={reduceMotion}
      />
    ),
    [reduceMotion],
  );
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
      <ScrollFade visible={fade.visible} style={styles.history}>
        <FlatList
          maintainVisibleContentPosition={{minIndexForVisible: 1}}
          ref={list}
          data={messages}
          keyExtractor={item => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.messages}
          onLayout={fade.onLayout}
          scrollEventThrottle={16}
          onScroll={event => {
            fade.onScroll(event);
            const {contentOffset, contentSize, layoutMeasurement} =
              event.nativeEvent;
            follow.current =
              contentOffset.y + layoutMeasurement.height >=
              contentSize.height - 48;
          }}
          onContentSizeChange={(width, height) => {
            fade.onContentSizeChange(width, height);
            if (follow.current) {
              list.current?.scrollToEnd({animated: false});
            }
          }}
          ListHeaderComponent={
            hasOlder ? (
              <FocusPressable
                accessibilityRole="button"
                accessibilityLabel="Load earlier messages"
                disabled={loadingOlder}
                onPress={() => {
                  follow.current = false;
                  onLoadOlder();
                }}
                style={styles.earlier}>
                <Text style={styles.muted}>
                  {loadingOlder ? 'Loading earlier…' : 'Load earlier messages'}
                </Text>
              </FocusPressable>
            ) : null
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.title}>What’s on your mind?</Text>
              <Text style={styles.muted}>
                Ask about a conversation, a task, or something you want to
                remember.
              </Text>
            </View>
          }
          ListFooterComponent={
            busy ? <ChatThinking reduceMotion={reduceMotion} desktop /> : null
          }
        />
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
