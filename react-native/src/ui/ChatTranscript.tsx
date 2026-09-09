import React, {memo, useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {OmiAvatar} from './OmiAvatar';
import {ChatMessageContent} from './ChatMessageContent';
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
  const streaming = isStreamingAssistant(message);
  const waiting = streaming && message.text === '';
  return (
    <Animated.View
      accessibilityLabel={
        message.generationOutcome === 'failed'
          ? 'Failed response'
          : waiting
          ? 'Waiting for response'
          : undefined
      }
      accessibilityLiveRegion={streaming ? 'polite' : undefined}
      accessibilityState={streaming ? {busy: true} : undefined}
      accessible={waiting || message.generationOutcome === 'failed'}
      style={[
        styles.chatMessageRow,
        human ? styles.chatMessageRowHuman : styles.chatMessageRowAi,
        {opacity, transform: [{translateY}]},
      ]}>
      {!human && (
        <OmiAvatar
          tone={desktop ? 'ink' : 'identity'}
          inkColor={desktop ? token.color.ink : undefined}
          animate={streaming}
          reduceMotion={reduceMotion}
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
            human ? transcriptStyles.human : styles.chatBubbleAi,
            desktop && !human && desktopStyles.ai,
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
          ) : human ? (
            <Text
              selectable
              style={[styles.message, desktop && desktopStyles.text]}>
              {message.text}
            </Text>
          ) : waiting ? (
            <View accessible={false} style={transcriptStyles.skeleton}>
              {[100, 86, 62].map(width => (
                <View
                  key={width}
                  style={[
                    transcriptStyles.line,
                    desktop && transcriptStyles.desktopLine,
                    {width: `${width}%`},
                  ]}
                />
              ))}
            </View>
          ) : (
            <ChatMessageContent
              text={message.text}
              style={[styles.message, desktop && desktopStyles.text]}
              streaming={streaming}
              reduceMotion={reduceMotion}
            />
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

function ChatThinking({
  reduceMotion,
  desktop = false,
}: {
  reduceMotion: boolean;
  desktop?: boolean;
}) {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (reduceMotion) {
      opacity.setValue(1);
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          duration: 700,
          toValue: 0.45,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          duration: 700,
          toValue: 1,
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [opacity, reduceMotion]);
  return (
    <View
      accessible
      accessibilityLabel="Waiting for response"
      accessibilityLiveRegion="polite"
      accessibilityState={{busy: true}}
      style={[styles.chatMessageRow, styles.chatMessageRowAi]}>
      <OmiAvatar
        tone="ink"
        inkColor={desktop ? token.color.ink : undefined}
        animate
        reduceMotion={reduceMotion}
      />
      <Animated.View
        accessible={false}
        style={[
          styles.chatBubble,
          styles.chatBubbleAi,
          desktop && desktopStyles.ai,
          transcriptStyles.skeleton,
          {opacity},
        ]}>
        {[100, 86, 62].map(width => (
          <View
            key={width}
            style={[
              transcriptStyles.line,
              desktop && transcriptStyles.desktopLine,
              {width: `${width}%`},
            ]}
          />
        ))}
      </Animated.View>
    </View>
  );
}

export {ChatMessageRow, ChatThinking};

const desktopStyles = StyleSheet.create({
  column: {maxWidth: '82%'},
  ai: {backgroundColor: token.color.glassQuiet, borderWidth: 0},
  text: {color: token.color.ink, fontSize: 15, lineHeight: 24},
  time: {color: token.color.inkFaint, fontSize: 11},
});

const transcriptStyles = StyleSheet.create({
  human: {
    backgroundColor: 'transparent',
    borderWidth: 0,
    paddingHorizontal: 0,
    paddingVertical: 4,
  },
  skeleton: {width: 260, maxWidth: '80%', gap: 10},
  line: {
    height: 10,
    borderRadius: 5,
    backgroundColor: 'rgba(255,255,255,0.18)',
  },
  desktopLine: {backgroundColor: token.color.glassSelected},
});
