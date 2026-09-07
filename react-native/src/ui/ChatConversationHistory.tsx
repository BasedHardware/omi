import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {useChatConversationHistory} from '../chatConversationHistory';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function ChatConversationHistory() {
  const {result, reload} = useChatConversationHistory(true);
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
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Reload chat messages"
            onPress={reload}
            style={styles.conversationTranscriptAction}>
            <Text style={styles.conversationDetailField}>Check again</Text>
          </FocusPressable>
        </>
      ) : result.messages.length === 0 ? (
        <Text style={styles.conversationDetailSummary}>
          No messages in this chat yet.
        </Text>
      ) : (
        result.messages.map(message => (
          <Text
            key={message.id}
            selectable
            style={styles.conversationTranscriptText}>
            {`${message.sender === 'human' ? 'You' : 'Omi'} · ${message.text}`}
          </Text>
        ))
      )}
    </View>
  );
}
