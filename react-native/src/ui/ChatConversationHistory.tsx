import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {chatHistoryHasOlder} from '../chatClient';
import {useChatConversationHistory} from '../chatConversationHistory';
import {
  chatClockLabel,
  chatMessageDisplayText,
  chatSenderCopy,
  visibleDisplayText,
} from '../desktopReadClient';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function ChatConversationHistory({
  conversationId,
}: {
  conversationId: string;
}) {
  const {result, reload, loadingOlder, loadOlder, olderNotice, olderRetryable} =
    useChatConversationHistory(true, conversationId);
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
      ) : (
        <>
          {olderNotice !== null && (
            <Text
              accessibilityRole="alert"
              style={styles.conversationDetailSummary}>
              {olderNotice}
            </Text>
          )}
          {chatHistoryHasOlder(result.hasOlder, result.olderCursor) &&
            olderRetryable && (
              <FocusPressable
                accessibilityLabel="Load older messages"
                accessibilityRole="button"
                disabled={loadingOlder}
                onPress={() => {
                  void loadOlder();
                }}
                style={styles.conversationTranscriptAction}>
                <Text style={styles.conversationDetailField}>
                  {loadingOlder ? 'Loading older…' : 'Load older messages'}
                </Text>
              </FocusPressable>
            )}
          {result.messages.length === 0 ? (
            result.hasOlder ? null : (
              <Text style={styles.conversationDetailSummary}>
                No messages in this chat yet.
              </Text>
            )
          ) : (
            result.messages.map(message => {
              const sender = chatSenderCopy(message.sender);
              const body = chatMessageDisplayText(message);
              return (
                <View key={message.id}>
                  <Text selectable style={styles.conversationTranscriptText}>
                    {`${sender} · ${body}`}
                  </Text>
                  {message.generationOutcome === 'cancelled' &&
                  visibleDisplayText(message.text) !== '' ? (
                    <Text style={styles.conversationDetailField}>
                      Response stopped
                    </Text>
                  ) : null}
                  <Text style={styles.conversationDetailField}>
                    {chatClockLabel(message.createdAt, Date.now()) ||
                      'Time unavailable'}
                  </Text>
                </View>
              );
            })
          )}
        </>
      )}
    </View>
  );
}
