import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {useChatConversationHistory} from '../chatConversationHistory';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function ChatConversationHistory({
  conversationId,
}: {
  conversationId: string;
}) {
  const {result, reload, loadingOlder, loadOlder} = useChatConversationHistory(
    true,
    conversationId,
  );
  return (
    <View style={styles.conversationDetailFields}>
      <Text accessibilityRole="header" style={styles.resultTitle}>
        Messages
      </Text>
      {result.status === 'loading' || result.status === 'idle' ? (
        <View accessibilityLiveRegion="polite">
          <ActivityIndicator color="#aaaaaa" />
          <Text style={styles.conversationDetailSummary}>Loading chat…</Text>
        </View>
      ) : result.status === 'error' ? (
        <>
          <Text
            accessibilityRole="alert"
            style={styles.conversationDetailSummary}>
            {result.error}
          </Text>
          {result.canReload && (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Reload chat messages"
              onPress={reload}
              style={styles.conversationTranscriptAction}>
              <Text style={styles.conversationDetailField}>Check again</Text>
            </FocusPressable>
          )}
        </>
      ) : result.messages.length === 0 ? (
        <Text style={styles.conversationDetailSummary}>
          No messages in this chat yet.
        </Text>
      ) : (
        <>
          {result.hasOlder && result.olderCursor !== null && (
            <FocusPressable
              accessibilityLabel="Load older messages"
              accessibilityRole="button"
              disabled={loadingOlder}
              onPress={() => {
                void loadOlder();
              }}
              style={styles.conversationTranscriptAction}>
              <Text style={styles.conversationDetailField}>
                {loadingOlder ? 'Loading older…' : 'Load older'}
              </Text>
            </FocusPressable>
          )}
          {result.messages.map(message => (
            <Text
              key={message.id}
              selectable
              style={styles.conversationTranscriptText}>
              {`${message.sender === 'human' ? 'You' : 'Omi'} · ${
                message.text
              }`}
            </Text>
          ))}
        </>
      )}
    </View>
  );
}
