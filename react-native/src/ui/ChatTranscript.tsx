import React, {memo, useEffect, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  Image,
  Text,
  View,
  type StyleProp,
  type TextStyle,
} from 'react-native';
import type {ChatMessage} from '../chatClient';
import {
  appImageUrl,
  chatAppAttributionCopy,
  chatAttachmentDisplayName,
  chatAttachmentThumbnailUrl,
  chatClockLabel,
  chatDaySummaryCopy,
  chatDaySummaryItems,
  chatDaySummaryRowCopy,
  chatMemoryCitationCopy,
  chatHumanQuotedContextCopy,
  chatMessageDisplayText,
  chatSenderCopy,
  paintedChatContentBlock,
  chatDiscoveryShowMoreCopy,
  chatDiscoveryShowLessCopy,
  visibleDisplayText,
  type TaskCardLookup,
  type GoalLinkLookup,
  type MemoryLinkLookup,
} from '../desktopReadClient';
import {OmiAvatar} from './OmiAvatar';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

function ChatContentBlockRow({
  block,
  tasks,
  goals,
  memories,
  textStyle,
}: {
  block: NonNullable<ChatMessage['contentBlocks']>[number];
  tasks?: readonly TaskCardLookup[];
  goals?: readonly GoalLinkLookup[];
  memories?: readonly MemoryLinkLookup[];
  textStyle: StyleProp<TextStyle>;
}) {
  const [expanded, setExpanded] = useState(false);
  const painted = paintedChatContentBlock(block, tasks, expanded, goals, memories);
  const more = block.more === undefined ? '' : visibleDisplayText(block.more);
  const detail =
    block.detail === undefined ? '' : visibleDisplayText(block.detail);
  const hasMore = more !== '' && more !== detail;
  const showCopy = expanded
    ? chatDiscoveryShowLessCopy()
    : chatDiscoveryShowMoreCopy();
  return (
    <View
      accessibilityLabel={
        painted.title === undefined
          ? painted.eyebrow
          : `${painted.eyebrow}: ${painted.title}`
      }>
      <Text numberOfLines={1} style={textStyle}>
        {painted.eyebrow}
      </Text>
      {painted.title !== undefined ? (
        <Text numberOfLines={2} style={textStyle}>
          {painted.title}
        </Text>
      ) : null}
      {painted.detail !== undefined ? (
        <Text numberOfLines={6} style={textStyle}>
          {painted.detail}
        </Text>
      ) : null}
      {hasMore ? (
        <FocusPressable
          accessibilityLabel={showCopy}
          accessibilityRole="button"
          accessibilityState={{expanded}}
          onPress={() => setExpanded(value => !value)}>
          <Text style={textStyle}>{showCopy}</Text>
        </FocusPressable>
      ) : null}
    </View>
  );
}

export function ChatContentBlockList({
  blocks,
  tasks,
  goals,
  memories,
  textStyle,
}: {
  blocks: NonNullable<ChatMessage['contentBlocks']>;
  tasks?: readonly TaskCardLookup[];
  goals?: readonly GoalLinkLookup[];
  memories?: readonly MemoryLinkLookup[];
  textStyle: StyleProp<TextStyle>;
}) {
  return (
    <>
      {blocks.map((block, index) => (
        <ChatContentBlockRow
          key={index}
          block={block}
          tasks={tasks}
          goals={goals}
          memories={memories}
          textStyle={textStyle}
        />
      ))}
    </>
  );
}

function ChatAppImage({
  accessibilityLabel,
  uri,
}: {
  accessibilityLabel: string;
  uri: string;
}) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return null;
  }
  return (
    <Image
      accessibilityLabel={accessibilityLabel}
      onError={() => setFailed(true)}
      source={{uri}}
      style={styles.chatAppImage}
    />
  );
}

export function ChatAppAttribution({
  appImage,
  appName,
  human,
  textStyle,
}: {
  appImage?: string;
  appName?: string;
  human: boolean;
  textStyle: StyleProp<TextStyle>;
}) {
  if (human) {
    return null;
  }
  const appAttribution = chatAppAttributionCopy(appName);
  const uri = appImageUrl(appImage);
  if (appAttribution === '' && uri === null) {
    return null;
  }
  return (
    <View style={styles.chatAppAttributionRow}>
      {uri === null ? null : (
        <ChatAppImage
          accessibilityLabel={
            appAttribution === '' ? 'App image' : appAttribution
          }
          uri={uri}
        />
      )}
      {appAttribution === '' ? null : (
        <Text numberOfLines={1} style={[textStyle, {marginTop: 0}]}>
          {appAttribution}
        </Text>
      )}
    </View>
  );
}

const ChatMessageRow = memo(function ChatMessageRow({
  animate,
  compact,
  message,
  reduceMotion,
  tasks,
  goals,
  memories,
}: {
  animate: boolean;
  compact: boolean;
  message: ChatMessage;
  reduceMotion: boolean;
  tasks?: readonly TaskCardLookup[];
  goals?: readonly GoalLinkLookup[];
  memories?: readonly MemoryLinkLookup[];
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
  const quoted = human
    ? chatHumanQuotedContextCopy(message.text)
    : {context: null, remainder: message.text};
  const body = chatMessageDisplayText(
    quoted.context === null
      ? message
      : {...message, text: quoted.remainder},
  );
  const daySummary = chatDaySummaryCopy(message.type, message.createdAt);
  const summaryItems =
    daySummary === '' ? [] : chatDaySummaryItems(message.text);
  const showSummaryItems =
    daySummary !== '' && message.generationOutcome !== 'failed';
  const citations = (message.memories ?? []).map(memory =>
    chatMemoryCitationCopy(memory),
  );
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
        {quoted.context !== null ? (
          <Text numberOfLines={2} style={styles.cancelledLabel}>
            {quoted.context}
          </Text>
        ) : null}
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
        <ChatAppAttribution
          appImage={message.appImage}
          appName={message.appName}
          human={human}
          textStyle={styles.cancelledLabel}
        />
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
        {!human && (message.contentBlocks ?? []).length > 0 ? (
          <ChatContentBlockList
            blocks={message.contentBlocks ?? []}
            tasks={tasks}
            goals={goals}
            memories={memories}
            textStyle={styles.cancelledLabel}
          />
        ) : null}
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
