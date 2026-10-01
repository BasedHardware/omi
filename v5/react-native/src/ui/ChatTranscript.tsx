import React, {memo, useEffect, useRef, useState} from 'react';
import * as ReactNative from 'react-native';
import {
  Alert,
  Animated,
  Easing,
  Platform,
  Pressable,
  Text,
  View,
} from 'react-native';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {OmiAvatar} from './OmiAvatar';
import {ChatMessageContent} from './ChatMessageContent';
import {MaterialIcon, type MaterialIconName} from './MaterialIcon';
import {FocusPressable} from './Pressable';
import {OmiButton} from '../design/primitives';
import {chatCopySharesOnPhone, copyChatText} from './chatClipboard';
import {chatMessageMs, chatTimeLabel} from './chatTimeline';

// One transcript for every surface (docs/chat-ux.md): your words sit in a
// quiet bubble on the right; Omi answers as flat, full-width Markdown with no
// bubble and no avatar. The Omi mark appears only while Omi is thinking or
// still writing. Actions live in a small bar under a reply: always visible on
// the newest reply, on hover or keyboard focus elsewhere (long-press on
// phones). Day separators replace per-message timestamps.

// Read per render (not at import) so tests and previews can switch platform.
const isPhone = () => Platform.OS === 'ios' || Platform.OS === 'android';

type CopyState = 'ready' | 'copied' | 'shared' | 'failed';

function copyLabel(state: CopyState) {
  return state === 'copied'
    ? 'Copied'
    : state === 'shared'
    ? 'Shared'
    : state === 'failed'
    ? 'Copy unavailable'
    : chatCopySharesOnPhone()
    ? 'Share or copy response'
    : 'Copy response';
}

/** Small quiet icon action with a tooltip; reports focus so its bar can show. */
function ChatActionButton({
  icon,
  label,
  onPress,
  onFocusChange,
}: {
  icon: MaterialIconName;
  label: string;
  onPress: () => void;
  onFocusChange?: (focused: boolean) => void;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  return (
    <FocusPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      {...({tooltip: label, title: label} as object)}
      onPress={onPress}
      onFocus={() => onFocusChange?.(true)}
      onBlur={() => onFocusChange?.(false)}
      hitSlop={isPhone() ? 6 : 2}
      style={state => [
        styles.action,
        (state as {hovered?: boolean}).hovered && styles.actionHovered,
        state.pressed && styles.actionPressed,
      ]}>
      <MaterialIcon
        name={icon}
        size={theme.size.iconSmall}
        color={theme.color.inkSecondary}
      />
    </FocusPressable>
  );
}

/** Whether a reply row draws its action bar (and so reserves its height). */
export function chatReplyHasActionBar(message: ChatMessage, latest: boolean) {
  return (
    message.sender === 'ai' &&
    !isStreamingAssistant(message) &&
    message.text.trim() !== '' &&
    (!isPhone() || latest)
  );
}

const ChatMessageRow = memo(function ChatMessageRow({
  animate,
  compact,
  desktop = false,
  message,
  onRetry,
  onCopy,
  reduceMotion,
  latest = false,
}: {
  animate: boolean;
  /** Phone density (the pushed chat page and the legacy wide shell). */
  compact: boolean;
  desktop?: boolean;
  message: ChatMessage;
  onRetry?: () => void;
  onCopy?: (text: string) => Promise<void> | void;
  reduceMotion: boolean;
  /** The newest Omi reply keeps its action bar visible. */
  latest?: boolean;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
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
        duration: reduceMotion ? 1 : theme.motion.standard,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        duration: reduceMotion ? 1 : theme.motion.standard,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: true,
      }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [animate, opacity, reduceMotion, theme.motion.standard, translateY]);
  const human = message.sender === 'human';
  const streaming = isStreamingAssistant(message);
  const waiting = streaming && message.text === '';
  const failed = message.generationOutcome === 'failed';
  const cancelled = message.generationOutcome === 'cancelled';
  const retryable =
    failed && message.generationRetryable === true && onRetry !== undefined;
  const [copyState, setCopyState] = useState<CopyState>('ready');
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const resetCopy = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (resetCopy.current !== null) {
        clearTimeout(resetCopy.current);
      }
    },
    [],
  );
  const copy = async () => {
    try {
      let next: CopyState = 'copied';
      if (onCopy) {
        await onCopy(message.text);
      } else {
        const result = await copyChatText(message.text);
        if (result === 'dismissed') {
          return;
        }
        next = result;
      }
      setCopyState(next);
      if (resetCopy.current !== null) {
        clearTimeout(resetCopy.current);
      }
      resetCopy.current = setTimeout(() => setCopyState('ready'), 1600);
    } catch {
      setCopyState('failed');
    }
  };
  const ms = chatMessageMs(message.createdAt);
  const time = chatTimeLabel(ms);
  const timeHint = {
    accessibilityHint: `${human ? 'Sent' : 'Answered'} at ${time}`,
    ...({tooltip: time, title: time} as object),
  };
  const mobile = compact && !desktop;
  const textStyle = mobile ? styles.textMobile : styles.text;

  if (human) {
    return (
      <Animated.View
        style={[styles.humanRow, {opacity, transform: [{translateY}]}]}>
        <View
          {...timeHint}
          style={[
            styles.bubble,
            mobile ? styles.bubbleMobile : styles.bubbleDesktop,
          ]}>
          <Text selectable style={textStyle}>
            {message.text}
          </Text>
        </View>
      </Animated.View>
    );
  }

  const showActions = !streaming && message.text.trim() !== '';
  // Phones cannot hover: only the newest reply shows its bar; older replies
  // open the same actions with a long press.
  const barVisible = latest || hovered || focused;
  const openSheet = () => {
    const options = [chatCopySharesOnPhone() ? 'Share or Copy' : 'Copy'];
    if (retryable) {
      options.push('Try Again');
    }
    options.push('Cancel');
    const choose = (index: number) => {
      if (index === 0) {
        copy().catch(() => undefined);
      } else if (retryable && index === 1) {
        onRetry?.();
      }
    };
    // Namespace access: react-native-web has no ActionSheetIOS export.
    const sheet = (
      ReactNative as {ActionSheetIOS?: typeof ReactNative.ActionSheetIOS}
    ).ActionSheetIOS;
    if (Platform.OS === 'ios' && sheet) {
      sheet.showActionSheetWithOptions(
        {options, cancelButtonIndex: options.length - 1},
        choose,
      );
    } else {
      Alert.alert(
        'Response',
        undefined,
        options.map((label, index) => ({
          text: label,
          style: label === 'Cancel' ? 'cancel' : 'default',
          onPress: () => choose(index),
        })),
      );
    }
  };
  const body = (
    <>
      {waiting ? (
        <ChatThinking reduceMotion={reduceMotion} desktop={!mobile} inline />
      ) : failed ? (
        <View style={styles.failure}>
          <MaterialIcon
            name="info"
            size={theme.size.iconSmall}
            color={theme.color.danger}
          />
          <Text selectable style={[textStyle, styles.failureText]}>
            {message.generationRetryable === true
              ? 'Response failed. Try again.'
              : 'Response failed.'}
          </Text>
          {retryable ? (
            <OmiButton label="Try Again" compact onPress={onRetry!} />
          ) : null}
        </View>
      ) : (
        <ChatMessageContent
          text={message.text}
          style={[textStyle, cancelled && styles.cancelledText]}
          streaming={streaming}
          reduceMotion={reduceMotion}
        />
      )}
      {streaming && !waiting ? (
        <View style={styles.writing}>
          <OmiAvatar
            tone="ink"
            size={14}
            inkColor={theme.color.ink}
            animate
            reduceMotion={reduceMotion}
          />
        </View>
      ) : null}
      {cancelled ? <Text style={styles.meta}>Response stopped</Text> : null}
      {showActions && (!isPhone() || latest) ? (
        <View
          style={[styles.bar, !barVisible && styles.barHidden]}
          accessibilityLabel="Response actions">
          <ChatActionButton
            icon={
              copyState === 'copied' || copyState === 'shared'
                ? 'check'
                : 'content_copy'
            }
            label={copyLabel(copyState)}
            onPress={() => {
              copy().catch(() => undefined);
            }}
            onFocusChange={setFocused}
          />
        </View>
      ) : null}
    </>
  );
  const rowProps = {
    accessibilityLabel: failed
      ? 'Failed response'
      : waiting
      ? 'Waiting for response'
      : undefined,
    accessibilityLiveRegion: streaming ? ('polite' as const) : undefined,
    accessibilityState: streaming ? {busy: true} : undefined,
    accessible: waiting || failed ? true : undefined,
  };
  return (
    <Animated.View
      {...rowProps}
      {...(waiting ? {} : timeHint)}
      {...({
        onMouseEnter: () => setHovered(true),
        onMouseLeave: () => setHovered(false),
      } as object)}
      style={[styles.aiRow, {opacity, transform: [{translateY}]}]}>
      {isPhone() && showActions && !latest ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Response"
          accessibilityHint="Long press for Copy and Try Again"
          delayLongPress={350}
          onLongPress={openSheet}>
          {body}
        </Pressable>
      ) : (
        body
      )}
    </Animated.View>
  );
});

/**
 * Omi is thinking: the animated Omi mark with a quiet "Thinking…" label. The
 * label pulses gently; both stop under Reduce Motion.
 */
function ChatThinking({
  reduceMotion,
  desktop = false,
  inline = false,
}: {
  reduceMotion: boolean;
  desktop?: boolean;
  /** Rendered inside a pending reply row that already owns the live region. */
  inline?: boolean;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
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
      {...(inline
        ? {}
        : {
            accessible: true,
            accessibilityLabel: 'Waiting for response',
            accessibilityLiveRegion: 'polite' as const,
            accessibilityState: {busy: true},
          })}
      style={[styles.thinking, !inline && styles.aiRow]}>
      <OmiAvatar
        tone="ink"
        size={desktop ? 18 : 22}
        inkColor={theme.color.ink}
        animate
        reduceMotion={reduceMotion}
      />
      <Animated.View accessible={false} style={{opacity}}>
        <Text style={styles.thinkingText}>Thinking…</Text>
      </Animated.View>
    </View>
  );
}

/** Centered quiet day label ("Today", "Yesterday", "Wed, Sep 23"). */
function ChatDaySeparator({label}: {label: string}) {
  const styles = useOmiStyles(createStyles);
  return (
    <View accessibilityRole="header" style={styles.day}>
      <Text style={styles.dayText}>{label}</Text>
    </View>
  );
}

export {ChatMessageRow, ChatThinking, ChatDaySeparator};

const createStyles = (t: OmiTheme) => {
  // Chat reads longer than a list row: body type with a looser leading.
  const reading = {...t.type.body, lineHeight: t.type.body.lineHeight + 4};
  return {
    humanRow: {
      alignSelf: 'stretch' as const,
      alignItems: 'flex-end' as const,
    },
    bubble: {
      maxWidth: '75%' as const,
      borderRadius: t.radius.sheet,
      paddingHorizontal: t.density === 'desktop' ? t.space.lg : t.space.lg - 2,
      paddingVertical:
        t.density === 'desktop' ? t.space.sm + 2 : t.space.sm + 2,
    },
    // Quiet ink fill on desktop glass; the raised grey on phones.
    bubbleDesktop: {backgroundColor: t.color.fillSelected},
    bubbleMobile: {backgroundColor: t.color.surfaceRaised},
    text: {...reading, color: t.color.ink},
    textMobile: {
      ...t.type.body,
      lineHeight: t.type.body.lineHeight + 3,
      color: t.color.ink,
    },
    cancelledText: {color: t.color.inkSecondary},
    aiRow: {alignSelf: 'stretch' as const},
    failure: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      flexWrap: 'wrap' as const,
      gap: t.space.sm,
      alignSelf: 'flex-start' as const,
      paddingVertical: t.space.xs,
    },
    failureText: {color: t.color.ink},
    writing: {marginTop: t.space.sm, alignSelf: 'flex-start' as const},
    meta: {
      ...t.type.footnote,
      color: t.color.inkSecondary,
      marginTop: t.space.xs,
    },
    bar: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: t.space.xxs,
      marginTop: t.space.xs,
      marginLeft: -6,
    },
    barHidden: {opacity: 0},
    action: {
      width: t.density === 'desktop' ? 26 : 34,
      height: t.density === 'desktop' ? 26 : 34,
      borderRadius: t.radius.pill,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    },
    actionHovered: {backgroundColor: t.color.fill},
    actionPressed: {backgroundColor: t.color.fillPressed},
    thinking: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: t.space.sm + 2,
      paddingVertical: t.space.xs,
    },
    thinkingText: {...t.type.subhead, color: t.color.inkSecondary},
    day: {
      alignSelf: 'center' as const,
      paddingVertical: t.space.xs,
    },
    dayText: {
      ...t.type.footnote,
      fontWeight: '600' as const,
      color: t.color.inkSecondary,
    },
  };
};
