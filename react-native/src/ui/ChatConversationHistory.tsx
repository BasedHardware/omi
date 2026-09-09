import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {useChatConversationHistory} from '../chatConversationHistory';
import {FocusPressable} from './Pressable';
import {styles} from './styles';
import {desktopTokens} from '../desktop/tokens';

export function ChatConversationHistory({
  desktop = false,
}: {
  desktop?: boolean;
}) {
  const {result, reload} = useChatConversationHistory(true);
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  return (
    <View style={styles.conversationDetailFields}>
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Messages
      </Text>
      {result.status === 'loading' || result.status === 'idle' ? (
        <View accessibilityLiveRegion="polite">
          <ActivityIndicator color="#aaaaaa" />
          <Text style={[styles.conversationDetailSummary, ink]}>
            Loading chat…
          </Text>
        </View>
      ) : result.status === 'error' ? (
        <>
          <Text
            accessibilityRole="alert"
            style={[styles.conversationDetailSummary, ink]}>
            {result.error}
          </Text>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Reload chat messages"
            onPress={reload}
            style={styles.conversationTranscriptAction}>
            <Text style={[styles.conversationDetailField, ink]}>
              Check again
            </Text>
          </FocusPressable>
        </>
      ) : result.messages.length === 0 ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          No messages in this chat yet.
        </Text>
      ) : (
        result.messages.map(message => (
          <Text
            key={message.id}
            selectable
            style={[styles.conversationTranscriptText, ink]}>
            {`${message.sender === 'human' ? 'You' : 'Omi'} · ${message.text}`}
          </Text>
        ))
      )}
    </View>
  );
}
