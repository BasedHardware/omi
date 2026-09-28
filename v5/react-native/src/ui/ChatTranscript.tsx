import React, {memo, useEffect, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  Platform,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {OmiAvatar} from './OmiAvatar';
import {ChatMessageContent} from './ChatMessageContent';
import {OmiButton, OmiIconButton} from '../design/primitives';
import {omiBackend} from '../omiNative';
import {styles} from './styles';
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from '../desktop/DesktopTheme';

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
  onRetry,
  onCopy,
  reduceMotion,
}: {
  animate: boolean;
  compact: boolean;
  desktop?: boolean;
  message: ChatMessage;
  onRetry?: () => void;
  onCopy?: (text: string) => Promise<void> | void;
  reduceMotion: boolean;
}) {
  const {tokens: token} = useDesktopTheme();
  const desktopStyles = useDesktopStyleSheets(createDesktopStyles);
  const transcriptStyles = useDesktopStyleSheets(createTranscriptStyles);
  const mobileBubbles = useOmiStyles(createMobileBubbleStyles);
  const omiTheme = useOmiTheme();
  // The mark keeps its own white on dark; light mobile reads theme ink.
  const mobileInk =
    omiTheme.scheme === 'light' ? omiTheme.color.ink : undefined;
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
  const [copyState, setCopyState] = useState<
    'ready' | 'copied' | 'shared' | 'failed'
  >('ready');
  const copy = async () => {
    try {
      if (onCopy) {
        await onCopy(message.text);
      } else if (omiBackend?.copyToClipboard) {
        await omiBackend.copyToClipboard(message.text);
      } else if (typeof navigator !== 'undefined' && 'clipboard' in navigator) {
        await (
          navigator as Navigator & {
            clipboard: {writeText(text: string): Promise<void>};
          }
        ).clipboard.writeText(message.text);
      } else if (Platform.OS === 'ios' || Platform.OS === 'android') {
        const result = await Share.share({message: message.text});
        if (result.action !== Share.dismissedAction) {
          setCopyState('shared');
        }
        return;
      } else {
        throw new Error('Clipboard unavailable');
      }
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
  };
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
          tone={desktop || compact ? 'ink' : 'identity'}
          size={compact && !desktop ? 28 : 40}
          inkColor={desktop ? token.color.ink : mobileInk}
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
          compact && !desktop && transcriptStyles.mobileColumn,
          desktop && desktopStyles.column,
        ]}>
        <View
          style={[
            styles.chatBubble,
            human
              ? desktop
                ? desktopStyles.human
                : mobileBubbles.human
              : desktop
              ? styles.chatBubbleAi
              : mobileBubbles.ai,
            desktop && !human && desktopStyles.ai,
            message.generationOutcome === 'cancelled' &&
              styles.cancelledMessage,
          ]}>
          {message.generationOutcome === 'failed' ? (
            <Text
              selectable
              style={[
                styles.failedLabel,
                desktop ? desktopStyles.text : mobileBubbles.text,
              ]}>
              {message.generationRetryable === true
                ? 'Response failed. Try again.'
                : 'Response failed.'}
            </Text>
          ) : human ? (
            <Text
              selectable
              style={[
                styles.message,
                desktop ? desktopStyles.text : mobileBubbles.text,
              ]}>
              {message.text}
            </Text>
          ) : waiting ? (
            <View accessible={false} style={transcriptStyles.skeleton}>
              {[100, 86, 62].map(width => (
                <View
                  key={width}
                  style={[
                    transcriptStyles.line,
                    desktop ? transcriptStyles.desktopLine : mobileBubbles.line,
                    {width: `${width}%`},
                  ]}
                />
              ))}
            </View>
          ) : (
            <ChatMessageContent
              text={message.text}
              style={[
                styles.message,
                desktop ? desktopStyles.text : mobileBubbles.text,
              ]}
              streaming={streaming}
              reduceMotion={reduceMotion}
            />
          )}
        </View>
        {message.generationOutcome === 'cancelled' && (
          <Text style={[styles.cancelledLabel, !desktop && mobileBubbles.time]}>
            Response stopped
          </Text>
        )}
        {message.generationOutcome === 'failed' &&
          message.generationRetryable === true &&
          onRetry !== undefined && (
            <OmiButton
              label="Try Again"
              compact
              onPress={onRetry}
              style={transcriptStyles.action}
            />
          )}
        {/* Copy is a quiet icon beside the time, not a button per reply:
            long threads stay readable. The label carries the state. */}
        <View
          style={[transcriptStyles.meta, human && transcriptStyles.metaHuman]}>
          <Text
            style={[
              styles.chatTimestamp,
              human && styles.chatTimestampHuman,
              desktop ? desktopStyles.time : mobileBubbles.time,
            ]}>
            {formatChatTime(message.createdAt)}
          </Text>
          {!human && !waiting && message.text.trim() !== '' && (
            <OmiIconButton
              icon={
                copyState === 'copied' || copyState === 'shared'
                  ? 'check'
                  : 'content_copy'
              }
              label={
                copyState === 'copied'
                  ? 'Copied'
                  : copyState === 'shared'
                  ? 'Shared'
                  : copyState === 'failed'
                  ? 'Copy unavailable'
                  : Platform.OS === 'ios' || Platform.OS === 'android'
                  ? 'Share or copy response'
                  : 'Copy response'
              }
              size="small"
              quiet
              onPress={copy}
            />
          )}
        </View>
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
  const {tokens: token} = useDesktopTheme();
  const desktopStyles = useDesktopStyleSheets(createDesktopStyles);
  const transcriptStyles = useDesktopStyleSheets(createTranscriptStyles);
  const mobileBubbles = useOmiStyles(createMobileBubbleStyles);
  const omiTheme = useOmiTheme();
  const mobileInk =
    omiTheme.scheme === 'light' ? omiTheme.color.ink : undefined;
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
        inkColor={desktop ? token.color.ink : mobileInk}
        animate
        reduceMotion={reduceMotion}
      />
      <Animated.View
        accessible={false}
        style={[
          styles.chatBubble,
          desktop ? styles.chatBubbleAi : mobileBubbles.ai,
          desktop && desktopStyles.ai,
          transcriptStyles.skeleton,
          {opacity},
        ]}>
        {[100, 86, 62].map(width => (
          <View
            key={width}
            style={[
              transcriptStyles.line,
              desktop ? transcriptStyles.desktopLine : mobileBubbles.line,
              {width: `${width}%`},
            ]}
          />
        ))}
      </Animated.View>
    </View>
  );
}

export {ChatMessageRow, ChatThinking};

const createDesktopStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    column: {maxWidth: '82%'},
    // Mirrors the shipped Omi app: your words sit in a quiet bubble on the
    // right; Omi answers as flat text beside its avatar, with no bubble.
    human: {
      backgroundColor: token.color.glassStrong,
      borderWidth: 0,
      borderRadius: 18,
      paddingHorizontal: 16,
      paddingVertical: 12,
    },
    ai: {backgroundColor: 'transparent', borderWidth: 0},
    text: {color: token.color.ink, fontSize: 15, lineHeight: 24},
    time: {color: token.color.inkFaint, fontSize: 11},
  });

// Same convention as the shipped Omi apps on both platforms: your words sit
// in a quiet bubble on the right; Omi answers as flat text with no bubble.
const createMobileBubbleStyles = (t: OmiTheme) => ({
  human: {
    backgroundColor: t.color.surfaceRaised,
    borderWidth: 0,
    borderRadius: t.radius.sheet,
    paddingHorizontal: t.space.lg - 2,
    paddingVertical: t.space.sm + 2,
  },
  ai: {
    backgroundColor: 'transparent',
    borderWidth: 0,
    paddingHorizontal: 0,
    paddingVertical: t.space.xs,
  },
  // Mobile text reads the Omi theme so both appearances stay legible.
  text: {color: t.color.ink},
  time: {color: t.color.inkTertiary},
  line: {backgroundColor: t.color.fillSelected},
});

const createTranscriptStyles = (token: DesktopTokens) =>
  StyleSheet.create({
    action: {alignSelf: 'flex-start', marginTop: 4},
    meta: {flexDirection: 'row', alignItems: 'center', gap: 2},
    metaHuman: {justifyContent: 'flex-end'},
    mobileColumn: {flexShrink: 1, maxWidth: '85%'},
    skeleton: {width: 260, maxWidth: '80%', gap: 10},
    line: {
      height: 10,
      borderRadius: 5,
      backgroundColor: 'rgba(255,255,255,0.18)',
    },
    desktopLine: {backgroundColor: token.color.glassSelected},
  });
