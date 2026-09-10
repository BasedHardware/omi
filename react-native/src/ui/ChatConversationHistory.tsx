import React from 'react';
import {ActivityIndicator, Image, Text, View} from 'react-native';
import {chatHistoryHasOlder} from '../chatClient';
import {useChatConversationHistory} from '../chatConversationHistory';
import {
  chatAppAttributionCopy,
  chatAttachmentDisplayName,
  chatAttachmentThumbnailUrl,
  chatClockLabel,
  chatDaySummaryCopy,
  chatMemoryCitationCopy,
  chatMessageDisplayText,
  chatSenderCopy,
  visibleDisplayText,
} from '../desktopReadClient';
import {desktopTokens} from '../desktop/tokens';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function ChatConversationHistory({
  conversationId,
  desktop = false,
}: {
  conversationId: string;
  desktop?: boolean;
}) {
  const {result, reload, loadingOlder, loadOlder, olderNotice, olderRetryable} =
    useChatConversationHistory(true, conversationId);
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  return (
    <View style={styles.conversationDetailFields}>
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Messages
      </Text>
      {result.status === 'loading' || result.status === 'idle' ? (
        <View accessibilityLiveRegion="polite">
          <ActivityIndicator
            color={desktop ? desktopTokens.color.inkMuted : '#aaaaaa'}
          />
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
          {result.canReload && (
            <FocusPressable
              accessibilityRole="button"
              accessibilityLabel="Reload chat messages"
              onPress={reload}
              style={styles.conversationTranscriptAction}>
              <Text style={[styles.conversationDetailField, ink]}>
                Check again
              </Text>
            </FocusPressable>
          )}
        </>
      ) : (
        <>
          {olderNotice !== null && (
            <Text
              accessibilityRole="alert"
              style={[styles.conversationDetailSummary, ink]}>
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
                <Text style={[styles.conversationDetailField, ink]}>
                  {loadingOlder ? 'Loading older…' : 'Load older messages'}
                </Text>
              </FocusPressable>
            )}
          {result.messages.length === 0 ? (
            result.hasOlder ? null : (
              <Text style={[styles.conversationDetailSummary, ink]}>
                No messages in this chat yet.
              </Text>
            )
          ) : (
            result.messages.map(message => {
              const human = message.sender === 'human';
              const sender = chatSenderCopy(message.sender);
              const body = chatMessageDisplayText(message);
              const daySummary = chatDaySummaryCopy(message.type);
              const appAttribution = human
                ? ''
                : chatAppAttributionCopy(message.appName);
              const citations = (message.memories ?? []).flatMap(memory => {
                const copy = chatMemoryCitationCopy(memory);
                return copy === null ? [] : [copy];
              });
              return (
                <View key={message.id}>
                  <Text
                    selectable
                    style={[styles.conversationTranscriptText, ink]}>
                    {body === '' ? sender : `${sender} · ${body}`}
                  </Text>
                  {(message.attachments ?? []).flatMap((attachment, index) => {
                    const uri = chatAttachmentThumbnailUrl(attachment);
                    if (uri === null) {
                      return [];
                    }
                    return [
                      <Image
                        key={`thumb-${index}`}
                        accessibilityLabel={chatAttachmentDisplayName(
                          attachment.displayName,
                        )}
                        source={{uri}}
                        style={styles.chatAttachmentImage}
                      />,
                    ];
                  })}
                  {message.generationOutcome === 'cancelled' &&
                  visibleDisplayText(message.text) !== '' ? (
                    <Text style={[styles.conversationDetailField, ink]}>
                      Response stopped
                    </Text>
                  ) : null}
                  {daySummary !== '' ? (
                    <Text style={[styles.conversationDetailField, ink]}>
                      {daySummary}
                    </Text>
                  ) : null}
                  {appAttribution !== '' ? (
                    <Text
                      numberOfLines={1}
                      style={[styles.conversationDetailField, ink]}>
                      {appAttribution}
                    </Text>
                  ) : null}
                  {citations.map((copy, index) => (
                    <Text
                      key={index}
                      numberOfLines={1}
                      style={[styles.conversationDetailField, ink]}>
                      {copy}
                    </Text>
                  ))}
                  {(message.evidence ?? []).map((item, index) => (
                    <View key={`evidence-${index}`}>
                      <Text
                        numberOfLines={1}
                        style={[styles.conversationDetailField, ink]}>
                        {item.title}
                      </Text>
                      <Text
                        numberOfLines={2}
                        style={[styles.conversationDetailField, ink]}>
                        {item.detail}
                      </Text>
                    </View>
                  ))}
                  {!human &&
                    (message.contentBlocks ?? []).map((item, index) => (
                      <View key={`block-${index}`}>
                        <Text
                          numberOfLines={1}
                          style={[styles.conversationDetailField, ink]}>
                          {item.eyebrow}
                        </Text>
                        {item.title !== undefined ? (
                          <Text
                            numberOfLines={2}
                            style={[styles.conversationDetailField, ink]}>
                            {item.title}
                          </Text>
                        ) : null}
                        {item.detail !== undefined ? (
                          <Text
                            numberOfLines={6}
                            style={[styles.conversationDetailField, ink]}>
                            {item.detail}
                          </Text>
                        ) : null}
                      </View>
                    ))}
                  <Text style={[styles.conversationDetailField, ink]}>
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
