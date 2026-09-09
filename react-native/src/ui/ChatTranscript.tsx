import React, {memo, useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {OmiAvatar} from './OmiAvatar';
import {styles} from './styles';
import {desktopTokens as token} from '../desktop/tokens';

function formatChatTime(createdAt: number): string {
  const milliseconds =
    createdAt > 100_000_000_000 ? createdAt : createdAt * 1000;
  return new Date(milliseconds).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

const ChatMessageRow = memo(function ChatMessageRow({
  animate,
  compact,
  desktop = false,
  message,
  reduceMotion,
}: {
  animate: boolean;
  compact: boolean;
  desktop?: boolean;
  message: ChatMessage;
  reduceMotion: boolean;
}) {
  const opacity = useRef(new Animated.Value(animate ? 0 : 1)).current;
  const translateY = useRef(
    new Animated.Value(animate && !reduceMotion ? 10 : 0),
  ).current;
  useEffect(() => {
    if (!animate) {
      opacity.setValue(1);
      translateY.setValue(0);
      return;
    }
    const animation = Animated.parallel([
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
    ]);
    animation.start();
    return () => animation.stop();
  }, [animate, opacity, reduceMotion, translateY]);
  const human = message.sender === 'human';
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
      {!human && (
        <OmiAvatar
          tone={desktop ? 'ink' : 'identity'}
          inkColor={desktop ? token.color.ink : undefined}
        />
      )}
      <View
        style={[
          styles.chatMessageColumn,
          compact
            ? styles.chatMessageColumnCompact
            : styles.chatMessageColumnDesktop,
          human && styles.chatMessageColumnHuman,
          desktop && desktopStyles.column,
        ]}>
        <View
          style={[
            styles.chatBubble,
            human ? styles.chatBubbleHuman : styles.chatBubbleAi,
            desktop && (human ? desktopStyles.human : desktopStyles.ai),
            message.generationOutcome === 'cancelled' &&
              styles.cancelledMessage,
          ]}>
          {message.generationOutcome === 'failed' ? (
            <Text
              selectable
              style={[styles.failedLabel, desktop && desktopStyles.text]}>
              {message.generationRetryable === true
                ? 'Response failed. Try again.'
                : 'Response failed.'}
            </Text>
          ) : (
            <Text
              selectable
              style={[styles.message, desktop && desktopStyles.text]}>
              {message.text}
            </Text>
          )}
        </View>
        {message.generationOutcome === 'cancelled' && (
          <Text style={styles.cancelledLabel}>Response stopped</Text>
        )}
        <Text
          style={[
            styles.chatTimestamp,
            human && styles.chatTimestampHuman,
            desktop && desktopStyles.time,
          ]}>
          {formatChatTime(message.createdAt)}
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

const desktopStyles = StyleSheet.create({
  column: {maxWidth: '82%'},
  human: {backgroundColor: token.color.glassSelected},
  ai: {backgroundColor: 'transparent', borderWidth: 0, paddingLeft: 4},
  text: {color: token.color.ink, fontSize: 15, lineHeight: 24},
  time: {color: token.color.inkFaint, fontSize: 11},
});
