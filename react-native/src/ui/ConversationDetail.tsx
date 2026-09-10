import React from 'react';
import {ActivityIndicator, Text, View} from 'react-native';
import {
  clockLabel,
  conversationCaptureCopy,
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationHasFinishClock,
  conversationStatusCopy,
  conversationTranscriptDurationCopy,
  conversationVisibilityCopy,
  formatConversationDuration,
  legacyTranscriptCanDisplaySeconds,
  legacyTranscriptTimestampCopy,
  visibleDisplayText,
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

function ConversationClockFields({
  conversation,
  ink,
  locked,
  durationCopy,
}: {
  conversation: ConversationProjection;
  ink?: {color: string};
  locked?: boolean;
  durationCopy?: string | null;
}) {
  const showLocked = locked === true || conversation.locked;
  const captureCopy = conversationCaptureCopy(conversation.capturedAtMs);
  const visibilityCopy = conversationVisibilityCopy(conversation.visibility);
  const wallDuration =
    durationCopy === undefined && conversationHasFinishClock(conversation)
      ? formatConversationDuration(
          conversation.startedAt,
          conversation.finishedAt,
        )
      : null;
  const duration = durationCopy === undefined ? wallDuration : durationCopy;
  return (
    <View style={styles.conversationDetailFields}>
      {captureCopy !== null ? (
        <Text style={[styles.conversationDetailField, ink]}>{captureCopy}</Text>
      ) : null}
      <Text style={[styles.conversationDetailField, ink]}>
        Started ·{' '}
        {formatConversationDate(
          conversation.startedAt ?? conversation.createdAt,
        )}
      </Text>
      {conversationHasFinishClock(conversation) ? (
        <Text style={[styles.conversationDetailField, ink]}>
          Finished · {formatConversationDate(conversation.finishedAt)}
        </Text>
      ) : null}
      {duration !== null ? (
        <Text style={[styles.conversationDetailField, ink]}>
          Duration · {duration}
        </Text>
      ) : null}
      <Text style={[styles.conversationDetailField, ink]}>
        Status · {conversationStatusCopy(conversation.status)}
      </Text>
      {conversation.starred ? (
        <Text
          accessibilityLabel="Starred conversation"
          style={[styles.conversationDetailField, ink]}>
          Starred
        </Text>
      ) : null}
      {showLocked ? (
        <Text style={[styles.conversationDetailField, ink]}>Locked</Text>
      ) : null}
      {conversation.discarded ? (
        <Text style={[styles.conversationDetailField, ink]}>Discarded</Text>
      ) : null}
      {visibilityCopy === null ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {visibilityCopy}
        </Text>
      )}
    </View>
  );
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
      <ConversationClockFields conversation={conversation} ink={ink} />
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
  const actionItems = (detail.actionItems ?? []).flatMap(item => {
    const description = visibleDisplayText(item.description);
    if (description === '') {
      return [];
    }
    return [{...item, description}];
  });
  const showLegacyClocks =
    detail.transcript.status === 'loaded' &&
    legacyTranscriptCanDisplaySeconds(detail.transcript.segments);
  const transcriptSegments =
    detail.transcript.status === 'loaded'
      ? detail.transcript.segments.flatMap(segment => {
          const text = visibleDisplayText(segment.text);
          if (text === '') {
            return [];
          }
          const speaker =
            segment.speaker === null
              ? null
              : visibleDisplayText(segment.speaker);
          return [{...segment, text, speaker: speaker === '' ? null : speaker}];
        })
      : [];
  const address = conversation.discarded
    ? ''
    : visibleDisplayText(detail.locationAddress ?? '');
  const appSummary = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummary ?? '');
  const appSummaryName = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummaryName ?? '');
  const calendarTitle = visibleDisplayText(detail.calendarEvent?.title ?? '');
  const calendarAttendees = (detail.calendarEvent?.attendees ?? [])
    .map(name => visibleDisplayText(name))
    .filter(name => name !== '')
    .join(', ');
  const calendarStart = visibleDisplayText(
    detail.calendarEvent?.startCopy ?? '',
  );
  const calendarEnd = visibleDisplayText(detail.calendarEvent?.endCopy ?? '');
  const calendarTimes =
    calendarStart !== '' && calendarEnd !== ''
      ? `${calendarStart} – ${calendarEnd}`
      : calendarStart !== ''
      ? calendarStart
      : calendarEnd;
  const folderName = visibleDisplayText(detail.folderName ?? '');
  const externalText = visibleDisplayText(detail.externalText ?? '');
  const showExternalTranscript =
    externalText !== '' &&
    (detail.photoCount === undefined || detail.photoCount <= 0) &&
    (detail.transcript.status === 'unavailable' ||
      transcriptSegments.length === 0);
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
      {appSummaryName === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {appSummaryName}
        </Text>
      )}
      {appSummary === '' ? null : (
        <Text selectable style={[styles.conversationDetailSummary, ink]}>
          {appSummary}
        </Text>
      )}
      <ConversationClockFields
        conversation={conversation}
        ink={ink}
        locked={detail.locked}
        durationCopy={
          detail.transcript.status === 'loaded'
            ? conversationTranscriptDurationCopy(detail.transcript.segments)
            : null
        }
      />
      {address === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>{address}</Text>
      )}
      {calendarTitle === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {calendarTitle}
        </Text>
      )}
      {calendarTimes === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {calendarTimes}
        </Text>
      )}
      {calendarAttendees === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {calendarAttendees}
        </Text>
      )}
      {detail.photoCount !== undefined && detail.photoCount > 0 ? (
        <Text style={[styles.conversationDetailField, ink]}>
          {`${detail.photoCount} photos`}
        </Text>
      ) : null}
      {(detail.photoCaptions ?? []).flatMap((caption, index) => {
        const copy = visibleDisplayText(caption);
        return copy === ''
          ? []
          : [
              <Text
                key={`photo-caption-${index}`}
                style={[styles.conversationDetailField, ink]}>
                {copy}
              </Text>,
            ];
      })}
      {folderName === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>{folderName}</Text>
      )}
      {detail.sections.flatMap((section, index) => {
        const heading = visibleDisplayText(section.heading);
        const bodyMarkdown = visibleDisplayText(section.bodyMarkdown);
        if (heading === '' && bodyMarkdown === '') {
          return [];
        }
        return [
          <View key={index} style={styles.conversationDetailFields}>
            {heading !== '' ? (
              <Text
                accessibilityRole="header"
                style={[styles.resultTitle, ink]}>
                {heading}
              </Text>
            ) : null}
            {bodyMarkdown !== '' ? (
              <Text selectable style={[styles.conversationTranscriptText, ink]}>
                {bodyMarkdown}
              </Text>
            ) : null}
          </View>,
        ];
      })}
      {actionItems.length > 0 ? (
        <>
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            Action Items
          </Text>
          {actionItems.map((item, index) => (
            <View key={index} style={styles.conversationDetailFields}>
              <Text selectable style={[styles.conversationTranscriptText, ink]}>
                {item.description}
              </Text>
              {item.completed ? (
                <Text style={[styles.conversationDetailField, ink]}>
                  Completed
                </Text>
              ) : null}
            </View>
          ))}
        </>
      ) : null}
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        Transcript
      </Text>
      {detail.transcript.status === 'unavailable' && !showExternalTranscript ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          {detail.locked
            ? 'This conversation is locked. Transcript unavailable.'
            : 'Transcript unavailable for this conversation.'}
        </Text>
      ) : showExternalTranscript ? (
        <Text selectable style={[styles.conversationTranscriptText, ink]}>
          {externalText}
        </Text>
      ) : transcriptSegments.length === 0 ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          The transcript is empty.
        </Text>
      ) : (
        transcriptSegments.map((segment, index) => {
          const namedPerson = visibleDisplayText(segment.personName ?? '');
          const speaker = segment.isUser
            ? 'You'
            : namedPerson !== ''
            ? namedPerson
            : segment.speaker?.replace(
                /^SPEAKER_(\d+)$/,
                (_, number: string) => `Speaker ${Number(number) + 1}`,
              ) || 'Speaker';
          const clock = showLegacyClocks
            ? legacyTranscriptTimestampCopy(segment.start, segment.end)
            : null;
          return (
            <View key={index} style={styles.conversationDetailFields}>
              <Text selectable style={[styles.conversationTranscriptText, ink]}>
                {speaker} · {segment.text}
              </Text>
              {clock !== null ? (
                <Text style={[styles.conversationDetailField, ink]}>
                  {clock}
                </Text>
              ) : null}
              {(segment.translations ?? []).flatMap((translation, tIndex) => {
                const copy = visibleDisplayText(translation);
                return copy === ''
                  ? []
                  : [
                      <Text
                        key={`translation-${index}-${tIndex}`}
                        style={[styles.conversationDetailField, ink]}>
                        {copy}
                      </Text>,
                    ];
              })}
              {(segment.translations ?? []).some(
                translation => visibleDisplayText(translation) !== '',
              ) ? (
                <Text style={[styles.conversationDetailField, ink]}>
                  translated by omi
                </Text>
              ) : null}
            </View>
          );
        })
      )}
    </>
  );
}
