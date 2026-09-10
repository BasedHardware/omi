import React, {memo, useEffect, useRef} from 'react';
import {Animated, Easing, Image, Text, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {
  chatAppAttributionCopy,
  chatAttachmentDisplayName,
  chatAttachmentThumbnailUrl,
  chatClockLabel,
  chatDaySummaryCopy,
  chatDaySummaryItems,
  chatDaySummaryRowCopy,
  chatMemoryCitationCopy,
  chatMessageDisplayText,
  chatSenderCopy,
  visibleDisplayText,
} from '../desktopReadClient';
import {OmiAvatar} from './OmiAvatar';
import {styles} from './styles';

const ChatMessageRow = memo(function ChatMessageRow({
  animate,
  compact,
  message,
  reduceMotion,
}: {
  animate: boolean;
  compact: boolean;
  message: ChatMessage;
  reduceMotion: boolean;
}) {
  const opacity = useRef(new Animated.Value(animate ? 0 : 1)).current;
  const translateY = useRef(
    new Animated.Value(animate && !reduceMotion ? 10 : 0),
  ).current;
  useEffect(() => {
    if (!animate) {
      return;
    }
    Animated.parallel([
      Animated.timing(opacity, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        duration: reduceMotion ? 1 : 200,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]).start();
  }, [animate, opacity, reduceMotion, translateY]);
  const human = message.sender === 'human';
  const body = chatMessageDisplayText(message);
  const daySummary = chatDaySummaryCopy(message.type, message.createdAt);
  const summaryItems =
    daySummary === '' ? [] : chatDaySummaryItems(message.text);
  const showSummaryItems =
    daySummary !== '' && message.generationOutcome !== 'failed';
  const appAttribution = human ? '' : chatAppAttributionCopy(message.appName);
  const citations = (message.memories ?? []).flatMap(memory => {
    const copy = chatMemoryCitationCopy(memory);
    return copy === null ? [] : [copy];
  });
  return (
    <Animated.View
      accessibilityLabel={
        message.generationOutcome === 'failed' ? 'Failed response' : undefined
      }
      style={[
        styles.chatMessageRow,
        human ? styles.chatMessageRowHuman : styles.chatMessageRowAi,
        {opacity, transform: [{translateY}]},
      ]}>
      {!human && message.sender === 'ai' && <OmiAvatar />}
      <View
        style={[
          styles.chatMessageColumn,
          compact
            ? styles.chatMessageColumnCompact
            : styles.chatMessageColumnDesktop,
          human && styles.chatMessageColumnHuman,
        ]}>
        {message.generationOutcome === 'failed' ||
        (!showSummaryItems && body !== '') ? (
          <View
            style={[
              styles.chatBubble,
              human ? styles.chatBubbleHuman : styles.chatBubbleAi,
              message.generationOutcome === 'cancelled' &&
                styles.cancelledMessage,
            ]}>
            {message.generationOutcome === 'failed' ? (
              <Text style={styles.failedLabel}>{body}</Text>
            ) : (
              <Text style={styles.message}>{body}</Text>
            )}
          </View>
        ) : null}
        {daySummary !== '' && (
          <Text style={styles.cancelledLabel}>{daySummary}</Text>
        )}
        {showSummaryItems &&
          summaryItems.map((item, index) => (
            <Text
              key={`summary-${index}`}
              numberOfLines={3}
              style={styles.message}>
              {chatDaySummaryRowCopy(index, item)}
            </Text>
          ))}
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
          visibleDisplayText(message.text) !== '' && (
            <Text style={styles.cancelledLabel}>Response stopped</Text>
          )}
        {appAttribution !== '' && (
          <Text numberOfLines={1} style={styles.cancelledLabel}>
            {appAttribution}
          </Text>
        )}
        {citations.map((copy, index) => (
          <Text key={index} numberOfLines={1} style={styles.cancelledLabel}>
            {copy}
          </Text>
        ))}
        {(message.evidence ?? []).map((item, index) => (
          <View
            key={`evidence-${index}`}
            accessibilityLabel={`${item.title}: ${item.detail}`}>
            <Text numberOfLines={1} style={styles.cancelledLabel}>
              {item.title}
            </Text>
            <Text numberOfLines={2} style={styles.cancelledLabel}>
              {item.detail}
            </Text>
          </View>
        ))}
        {!human &&
          (message.contentBlocks ?? []).map((item, index) => (
            <View
              key={`block-${index}`}
              accessibilityLabel={
                item.title === undefined
                  ? item.eyebrow
                  : `${item.eyebrow}: ${item.title}`
              }>
              <Text numberOfLines={1} style={styles.cancelledLabel}>
                {item.eyebrow}
              </Text>
              {item.title !== undefined && (
                <Text numberOfLines={2} style={styles.cancelledLabel}>
                  {item.title}
                </Text>
              )}
              {item.detail !== undefined && (
                <Text numberOfLines={6} style={styles.cancelledLabel}>
                  {item.detail}
                </Text>
              )}
            </View>
          ))}
        {message.sender === 'unknown' && (
          <Text style={styles.cancelledLabel}>
            {chatSenderCopy(message.sender)}
          </Text>
        )}
        <Text
          style={[styles.chatTimestamp, human && styles.chatTimestampHuman]}>
          {chatClockLabel(message.createdAt, Date.now()) || 'Time unavailable'}
        </Text>
      </View>
    </Animated.View>
  );
});

function ChatThinking({reduceMotion}: {reduceMotion: boolean}) {
  const dots = useRef([
    new Animated.Value(1),
    new Animated.Value(1),
    new Animated.Value(1),
  ]).current;
  useEffect(() => {
    if (reduceMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.stagger(
        150,
        dots.map(dot =>
          Animated.sequence([
            Animated.timing(dot, {
              duration: 300,
              toValue: 0.3,
              useNativeDriver: true,
            }),
            Animated.timing(dot, {
              duration: 300,
              toValue: 1,
              useNativeDriver: true,
            }),
          ]),
        ),
      ),
    );
    animation.start();
    return () => animation.stop();
  }, [dots, reduceMotion]);
  return (
    <View style={[styles.chatMessageRow, styles.chatMessageRowAi]}>
      <OmiAvatar animate reduceMotion={reduceMotion} />
      <View
        accessibilityLabel="Thinking"
        style={[styles.chatBubble, styles.chatBubbleAi]}>
        {reduceMotion ? (
          <Text style={styles.thinkingText}>Thinking…</Text>
        ) : (
          <View style={styles.thinkingDots}>
            {dots.map((opacity, index) => (
              <Animated.View
                key={index}
                style={[styles.thinkingDot, {opacity}]}
              />
            ))}
          </View>
        )}
      </View>
    </View>
  );
}

export {ChatMessageRow, ChatThinking};
