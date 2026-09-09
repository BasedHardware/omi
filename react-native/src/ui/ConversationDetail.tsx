import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {
  clockLabel,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationStatusCopy,
  type ConversationProjection,
} from '../desktopReadClient';
import {RecordingTranscript} from './RecordingTranscript';
import {ChatConversationHistory} from './ChatConversationHistory';
import {desktopTokens} from '../desktop/tokens';
import {styles} from './styles';
import {FocusPressable} from './Pressable';
import {useLegacyConversationDetail} from '../useLegacyConversationDetail';

export function formatConversationDate(value: string | null): string {
  if (value === null) {
    return 'Time unavailable';
  }
  const label = clockLabel(Date.parse(value), Date.now());
  return label === '' ? 'Time unavailable' : label;
}

export function formatConversationDuration(
  startedAt: string | null,
  finishedAt: string | null,
): string {
  if (startedAt === null || finishedAt === null) {
    return 'Duration unavailable';
  }
  const startedAtMs = Date.parse(startedAt);
  const finishedAtMs = Date.parse(finishedAt);
  if (
    !Number.isFinite(startedAtMs) ||
    startedAtMs <= 0 ||
    !Number.isFinite(finishedAtMs) ||
    finishedAtMs <= 0
  ) {
    return 'Duration unavailable';
  }
  const duration = finishedAtMs - startedAtMs;
  if (duration < 0) {
    return 'Duration unavailable';
  }
  if (duration < 60_000) {
    return '< 1 min';
  }
  const minutes = Math.round(duration / 60_000);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes === 0
    ? `${hours} hr`
    : `${hours} hr ${remainingMinutes} min`;
}

export function ConversationDetail({
  conversation,
  desktop = false,
  apiContract,
}: {
  conversation: ConversationProjection;
  desktop?: boolean;
  apiContract?: 'omi';
}) {
  if (apiContract === 'omi') {
    return (
      <LegacyConversationBody
        key={conversation.id}
        conversation={conversation}
        desktop={desktop}
      />
    );
  }
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  return (
    <>
      <Text style={[styles.conversationDetailTitle, ink]}>
        {conversationDisplayTitle(conversation)}
      </Text>
      <Text style={[styles.conversationDetailSummary, ink]}>
        {conversationDisplaySummary(conversation)}
      </Text>
      <View style={styles.conversationDetailFields}>
        {conversation.capturedAtMs !== undefined && (
          <Text style={[styles.conversationDetailField, ink]}>
            Captured (device time) ·{' '}
            {formatConversationDate(
              new Date(conversation.capturedAtMs).toISOString(),
            )}
          </Text>
        )}
        <Text style={[styles.conversationDetailField, ink]}>
          Started · {formatConversationDate(conversation.startedAt)}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Finished · {formatConversationDate(conversation.finishedAt)}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Duration ·{' '}
          {formatConversationDuration(
            conversation.startedAt,
            conversation.finishedAt,
          )}
        </Text>
        <Text style={[styles.conversationDetailField, ink]}>
          Status · {conversationStatusCopy(conversation.status)}
        </Text>
        {conversation.locked && (
          <Text style={[styles.conversationDetailField, ink]}>Locked</Text>
        )}
        {conversation.discarded && (
          <Text style={[styles.conversationDetailField, ink]}>Discarded</Text>
        )}
      </View>
      {conversation.source === 'omi' &&
        conversation.id.startsWith('recording:') &&
        conversation.id.length > 'recording:'.length && (
          <RecordingTranscript
            desktop={desktop}
            key={conversation.id}
            sessionId={conversation.id.slice('recording:'.length)}
            revision={conversation.updatedAt ?? undefined}
          />
        )}
      {conversation.source === 'chat' &&
        conversation.id.startsWith('chat:') &&
        conversation.id.length > 'chat:'.length && (
          <ChatConversationHistory
            desktop={desktop}
            key={conversation.id}
            conversationId={conversation.id}
          />
        )}
      {conversation.source === 'chat' &&
        !(
          conversation.id.startsWith('chat:') &&
          conversation.id.length > 'chat:'.length
        ) && (
          <Text style={[styles.conversationDetailSummary, ink]}>
            Chat history for this conversation is not available here.
          </Text>
        )}
      {conversation.source !== 'chat' &&
        !(
          conversation.source === 'omi' &&
          conversation.id.startsWith('recording:') &&
          conversation.id.length > 'recording:'.length
        ) && (
          <Text style={[styles.conversationDetailSummary, ink]}>
            A full transcript is not available for this conversation yet.
          </Text>
        )}
    </>
  );
}

function LegacyConversationBody({
  conversation,
  desktop,
}: {
  conversation: ConversationProjection;
  desktop: boolean;
}) {
  const {result, reload} = useLegacyConversationDetail(
    conversation.id,
    conversation.updatedAt,
  );
  const ink = desktop ? {color: desktopTokens.color.ink} : undefined;
  if (result.status === 'idle' || result.status === 'loading') {
    return (
      <View>
        <ActivityIndicator
          color={desktop ? desktopTokens.color.inkMuted : '#aaaaaa'}
        />
        <Text style={[styles.conversationDetailSummary, ink]}>
          Loading conversation…
        </Text>
      </View>
    );
  }
  if (result.status === 'error') {
    return (
      <View>
        <Text
          accessibilityRole="alert"
          style={[styles.conversationDetailSummary, ink]}>
          {result.error}
        </Text>
        <FocusPressable
          accessibilityRole="button"
          accessibilityLabel="Retry conversation details"
          onPress={reload}
          style={styles.conversationTranscriptAction}>
          <Text style={[styles.conversationDetailField, ink]}>Try again</Text>
        </FocusPressable>
      </View>
    );
  }
  const detail = result.value;
  return (
    <>
      <Text
        accessibilityRole="header"
        style={[styles.conversationDetailTitle, ink]}>
        {conversationDisplayTitle({
          title: detail.title,
          status: conversation.status,
        })}
      </Text>
      <Text selectable style={[styles.conversationDetailSummary, ink]}>
        {conversationDisplaySummary({
          summary: detail.summary,
          status: conversation.status,
        })}
      </Text>
      {detail.sections.map((section, index) => (
        <View key={index} style={styles.conversationDetailFields}>
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            {section.heading}
          </Text>
          <Text selectable style={[styles.conversationTranscriptText, ink]}>
            {section.bodyMarkdown}
          </Text>
        </View>
      ))}
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Transcript
      </Text>
      {detail.transcript.status === 'unavailable' ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          {detail.locked
            ? 'This conversation is locked. Transcript unavailable.'
            : 'Transcript unavailable for this conversation.'}
        </Text>
      ) : detail.transcript.segments.length === 0 ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          The transcript is empty.
        </Text>
      ) : (
        detail.transcript.segments.map((segment, index) => (
          <Text
            key={index}
            selectable
            style={[styles.conversationTranscriptText, ink]}>
            {segment.isUser
              ? 'You'
              : segment.speaker?.replace(
                  /^SPEAKER_(\d+)$/,
                  (_, number: string) => `Speaker ${Number(number) + 1}`,
                ) || 'Speaker'}{' '}
            · {segment.text}
          </Text>
        ))
      )}
    </>
  );
}
