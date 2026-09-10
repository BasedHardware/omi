import React, {memo, useEffect, useRef} from 'react';
import {Animated, Easing, Text, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {
  chatAppAttributionCopy,
  chatClockLabel,
  chatDaySummaryCopy,
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
  const daySummary = chatDaySummaryCopy(message.type);
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
        <View
          style={[
            styles.chatBubble,
            human ? styles.chatBubbleHuman : styles.chatBubbleAi,
            message.generationOutcome === 'cancelled' &&
              styles.cancelledMessage,
          ]}>
          {message.generationOutcome === 'failed' ? (
            <Text style={styles.failedLabel}>
              {chatMessageDisplayText(message)}
            </Text>
          ) : (
            <Text style={styles.message}>
              {chatMessageDisplayText(message)}
            </Text>
          )}
        </View>
        {message.generationOutcome === 'cancelled' &&
          visibleDisplayText(message.text) !== '' && (
            <Text style={styles.cancelledLabel}>Response stopped</Text>
          )}
        {daySummary !== '' && (
          <Text style={styles.cancelledLabel}>{daySummary}</Text>
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
