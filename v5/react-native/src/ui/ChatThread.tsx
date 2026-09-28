import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AccessibilityInfo,
  Platform,
  ScrollView,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {isStreamingAssistant, type ChatMessage} from '../chatClient';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import type {OmiTheme} from '../design/tokens';
import {MaterialIcon} from './MaterialIcon';
import {FocusPressable} from './Pressable';
import {
  ChatDaySeparator,
  ChatMessageRow,
  ChatThinking,
  chatReplyHasActionBar,
} from './ChatTranscript';
import {buildChatTimeline} from './chatTimeline';

/** Within this many points of the end counts as "at the latest message". */
export const CHAT_BOTTOM_SLOP = 48;

/**
 * The scrolling transcript shared by desktop Chat and the phone chat page.
 *
 * Stick-to-bottom: while you are at the end, new text keeps the view pinned
 * there. Scrolling away (wheel, drag, keys) stops following and a "Jump to
 * Latest" pill floats above the composer; sending (a new submission, or a new
 * local message) resumes following. Programmatic scroll events never count
 * as the user leaving the end.
 */
export function ChatThread({
  messages,
  busy,
  desktop,
  submission = 0,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  onRetry,
  shouldAnimate,
  scrollRef,
  onScroll,
  onJumpLatest,
  reduceMotion,
  header,
  footer,
  style,
}: {
  messages: readonly ChatMessage[];
  busy: boolean;
  desktop: boolean;
  submission?: number;
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => void;
  onRetry?: (message: ChatMessage) => void;
  shouldAnimate?: (id: string) => boolean;
  scrollRef?: React.RefObject<ScrollView | null>;
  onScroll?: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
  onJumpLatest?: () => void;
  reduceMotion: boolean;
  /** Rendered at the top of the scroll content (loading/error states). */
  header?: React.ReactNode;
  /** Rendered after the last message inside the scroll content. */
  footer?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
  const ownRef = useRef<ScrollView>(null);
  const list = scrollRef ?? ownRef;
  const follow = useRef(true);
  const userScrolling = useRef(false);
  const pointerScrolling = useRef(false);
  const [following, setFollowing] = useState(true);
  const scrollToBottom = useCallback(() => {
    if (follow.current) {
      list.current?.scrollToEnd({animated: false});
    }
  }, [list]);
  const setFollow = useCallback((value: boolean) => {
    follow.current = value;
    setFollowing(value);
  }, []);
  const jumpToLatest = useCallback(() => {
    setFollow(true);
    onJumpLatest?.();
    list.current?.scrollToEnd({animated: !reduceMotion});
  }, [list, onJumpLatest, reduceMotion, setFollow]);
  const beginUserScroll = useCallback(() => {
    userScrolling.current = true;
    setFollow(false);
  }, [setFollow]);
  // Web: wheel, touch, scrollbar drag and scroll keys are the user's intent.
  useLayoutEffect(() => {
    if (Platform.OS !== 'web') {
      return;
    }
    const node = (
      list.current as unknown as {getScrollableNode?: () => unknown} | null
    )?.getScrollableNode?.() as
      | (EventTarget & {ownerDocument: EventTarget})
      | undefined;
    if (!node) {
      return;
    }
    const pointerDown = (event: Event) => {
      if (event.target === node) {
        pointerScrolling.current = true;
        beginUserScroll();
      }
    };
    const pointerUp = () => {
      pointerScrolling.current = false;
      userScrolling.current = false;
    };
    const keyDown = (event: Event) => {
      if (
        'key' in event &&
        typeof event.key === 'string' &&
        [
          'ArrowUp',
          'ArrowDown',
          'PageUp',
          'PageDown',
          'Home',
          'End',
          ' ',
        ].includes(event.key)
      ) {
        beginUserScroll();
      }
    };
    node.addEventListener('wheel', beginUserScroll, {passive: true});
    node.addEventListener('touchmove', beginUserScroll, {passive: true});
    node.addEventListener('pointerdown', pointerDown);
    node.addEventListener('keydown', keyDown);
    node.ownerDocument.addEventListener('pointerup', pointerUp);
    node.ownerDocument.addEventListener('pointercancel', pointerUp);
    return () => {
      node.removeEventListener('wheel', beginUserScroll);
      node.removeEventListener('touchmove', beginUserScroll);
      node.removeEventListener('pointerdown', pointerDown);
      node.removeEventListener('keydown', keyDown);
      node.ownerDocument.removeEventListener('pointerup', pointerUp);
      node.ownerDocument.removeEventListener('pointercancel', pointerUp);
    };
  }, [beginUserScroll, list]);
  // Sending resumes following: an explicit submission from the host, or a
  // new local (optimistic) message at the end of the thread.
  const lastLocal = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].localOnly && messages[index].sender === 'human') {
        return messages[index].id;
      }
    }
    return null;
  }, [messages]);
  const seenLocal = useRef(lastLocal);
  useLayoutEffect(() => {
    userScrolling.current = false;
    setFollow(true);
  }, [submission, setFollow]);
  useLayoutEffect(() => {
    if (lastLocal !== null && lastLocal !== seenLocal.current) {
      userScrolling.current = false;
      setFollow(true);
    }
    seenLocal.current = lastLocal;
  }, [lastLocal, setFollow]);
  useLayoutEffect(() => {
    if (following) {
      scrollToBottom();
    }
  }, [following, submission, scrollToBottom]);
  // Screen readers hear when a reply finishes (or fails), not every token.
  const wasStreaming = useRef(false);
  useEffect(() => {
    const streaming = messages.some(isStreamingAssistant);
    let lastReply: ChatMessage | null = null;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].sender === 'ai') {
        lastReply = messages[index];
        break;
      }
    }
    if (wasStreaming.current && !streaming && lastReply !== null) {
      AccessibilityInfo.announceForAccessibility?.(
        lastReply.generationOutcome === 'failed'
          ? 'Omi’s response failed'
          : lastReply.generationOutcome === 'cancelled'
          ? 'Response stopped'
          : 'Omi replied',
      );
    }
    wasStreaming.current = streaming;
  }, [messages]);
  const timeline = useMemo(() => buildChatTimeline(messages), [messages]);
  const gap = {
    day: theme.space.xxl,
    afterDay: theme.space.md,
    grouped: theme.space.sm - 2,
    turn: desktop ? theme.space.xxl : theme.space.xl,
    // A reply's action bar already reserves a row of space below it.
    afterBar: theme.space.sm,
  };
  const showThinking = busy && !messages.some(isStreamingAssistant);
  const thinkingGap = {marginTop: messages.length > 0 ? gap.turn : 0};
  return (
    <View style={[styles.root, style]}>
      <ScrollView
        ref={list}
        accessibilityLabel="Chat transcript"
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode={desktop ? undefined : 'interactive'}
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          desktop ? styles.contentDesktop : styles.contentMobile,
        ]}
        onLayout={() => {
          scrollToBottom();
        }}
        onScrollBeginDrag={beginUserScroll}
        onScrollEndDrag={() => {
          userScrolling.current = false;
        }}
        onMomentumScrollBegin={() => {
          userScrolling.current = true;
        }}
        onMomentumScrollEnd={() => {
          userScrolling.current = false;
        }}
        scrollEventThrottle={16}
        onScroll={event => {
          const {contentOffset, contentSize, layoutMeasurement} =
            event.nativeEvent;
          const atBottom =
            contentOffset.y + layoutMeasurement.height >=
            contentSize.height - CHAT_BOTTOM_SLOP;
          if (atBottom && !follow.current) {
            // Back at the end by any means: follow again.
            setFollow(true);
          } else if (userScrolling.current && !atBottom) {
            setFollow(false);
          }
          if (
            userScrolling.current &&
            Platform.OS === 'web' &&
            !pointerScrolling.current
          ) {
            userScrolling.current = false;
          }
          onScroll?.(event);
        }}
        onContentSizeChange={() => {
          scrollToBottom();
        }}>
        {hasOlder ? (
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Load earlier messages"
            disabled={loadingOlder}
            onPress={() => {
              userScrolling.current = false;
              setFollow(false);
              onLoadOlder();
            }}
            style={press => [
              styles.earlier,
              (press as {hovered?: boolean}).hovered && styles.earlierHovered,
            ]}>
            <Text style={styles.earlierText}>
              {loadingOlder ? 'Loading Earlier…' : 'Load Earlier Messages'}
            </Text>
          </FocusPressable>
        ) : null}
        {header}
        {timeline.map((item, index) => {
          const previous = index > 0 ? timeline[index - 1] : null;
          const marginTop =
            previous === null && !hasOlder
              ? 0
              : item.kind === 'day'
              ? gap.day
              : previous?.kind === 'day'
              ? gap.afterDay
              : previous?.kind === 'message' &&
                chatReplyHasActionBar(previous.message, previous.latestReply)
              ? gap.afterBar
              : item.grouped
              ? gap.grouped
              : gap.turn;
          return item.kind === 'day' ? (
            <View key={item.key} style={{marginTop}}>
              <ChatDaySeparator label={item.label} />
            </View>
          ) : (
            <View key={item.key} style={{marginTop}}>
              <ChatMessageRow
                message={item.message}
                compact={!desktop}
                desktop={desktop}
                latest={item.latestReply}
                animate={shouldAnimate ? shouldAnimate(item.message.id) : false}
                reduceMotion={reduceMotion}
                onRetry={onRetry ? () => onRetry(item.message) : undefined}
              />
            </View>
          );
        })}
        {showThinking ? (
          <View style={thinkingGap}>
            <ChatThinking reduceMotion={reduceMotion} desktop={desktop} />
          </View>
        ) : null}
        {footer}
      </ScrollView>
      {!following && messages.length > 0 ? (
        <View pointerEvents="box-none" style={styles.jumpLayer}>
          <FocusPressable
            accessibilityRole="button"
            accessibilityLabel="Jump to Latest"
            onPress={jumpToLatest}
            style={press => [
              styles.jump,
              (press as {hovered?: boolean}).hovered && styles.jumpHovered,
              press.pressed && styles.jumpPressed,
            ]}>
            <MaterialIcon
              name="arrow_downward"
              size={theme.size.iconSmall}
              color={theme.color.ink}
            />
            <Text style={styles.jumpText}>Jump to Latest</Text>
          </FocusPressable>
        </View>
      ) : null}
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {flex: 1, minHeight: 0},
  scroll: {flex: 1},
  content: {flexGrow: 1},
  // Same column logic as the Activity feed: a centered reading column on the
  // window surface, no panel of its own.
  contentDesktop: {
    width: '100%' as const,
    maxWidth: t.layout.chatColumn + 2 * t.layout.pageGutter.desktop,
    alignSelf: 'center' as const,
    paddingHorizontal: t.layout.pageGutter.desktop,
    paddingTop: t.space.sm,
    paddingBottom: t.space.xxl,
  },
  contentMobile: {
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.lg,
    paddingBottom: t.space.lg,
  },
  earlier: {
    alignSelf: 'center' as const,
    minHeight: t.size.hitTarget,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.md,
    borderRadius: t.radius.pill,
  },
  earlierHovered: {backgroundColor: t.color.fill},
  earlierText: {
    ...t.type.subhead,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  jumpLayer: {
    position: 'absolute' as const,
    left: 0,
    right: 0,
    bottom: t.space.md,
    alignItems: 'center' as const,
  },
  jump: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: t.space.xs + 2,
    minHeight: t.density === 'desktop' ? t.size.control : t.size.hitTarget,
    paddingHorizontal: t.space.md + 2,
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: t.color.separator,
    backgroundColor: t.color.surface,
  },
  jumpHovered: {backgroundColor: t.color.surfaceRaised},
  jumpPressed: {opacity: t.motion.pressedOpacity},
  jumpText: {...t.type.subhead, fontWeight: '600' as const, color: t.color.ink},
});
