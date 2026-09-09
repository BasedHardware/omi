import React, {useCallback, useRef} from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import ArrowUp from 'lucide-react-native/icons/arrow-up';
import Square from 'lucide-react-native/icons/square';
import type {ChatMessage} from '../chatClient';
import {ChatMessageRow} from '../ui/ChatTranscript';
import {FocusPressable} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {ScrollFade, useScrollFade} from './ScrollFade';
import {desktopTokens as token} from './tokens';

type Props = {
  messages: ChatMessage[];
  draft: string;
  busy: boolean;
  canStop: boolean;
  error: string | null;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
};
export function DesktopChat({
  messages,
  draft,
  busy,
  canStop,
  error,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  onDraftChange,
  onSend,
  onStop,
}: Props) {
  const list = useRef<FlatList<ChatMessage>>(null);
  const follow = useRef(true);
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
            if (follow.current) list.current?.scrollToEnd({animated: false});
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
            busy ? (
              <ActivityIndicator
                accessibilityLabel="Omi is replying"
                color={token.color.inkMuted}
                style={styles.thinking}
              />
            ) : null
          }
        />
      </ScrollFade>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
      <View style={styles.composer}>
        <TextInput
          accessibilityLabel="Message Omi"
          placeholder="Message Omi…"
          placeholderTextColor={token.color.inkMuted}
          multiline
          value={draft}
          onChangeText={onDraftChange}
          style={styles.input}
        />
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel={canStop ? 'Stop' : busy ? 'Sending…' : 'Send'}
          disabled={!canStop && (busy || !draft.trim())}
          onPress={() => {
            follow.current = true;
            if (canStop) {
              onStop();
            } else if (!busy && draft.trim()) {
              onSend();
            }
          }}
          style={styles.send}>
          {canStop ? (
            <Square size={16} color={token.color.ink} />
          ) : (
            <ArrowUp size={18} color={token.color.ink} />
          )}
        </FocusPressable>
      </View>
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
  thinking: {padding: 12},
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 12,
    padding: 12,
    margin: 12,
    borderRadius: 20,
    backgroundColor: token.color.glassQuiet,
  },
  input: {
    flex: 1,
    minHeight: 30,
    maxHeight: 160,
    fontSize: 15,
    lineHeight: 22,
    color: token.color.ink,
  },
  send: {
    padding: 10,
    borderRadius: 16,
    backgroundColor: token.color.glassSelected,
  },
  error: {color: token.color.ink, paddingHorizontal: 24, fontSize: 13},
});
