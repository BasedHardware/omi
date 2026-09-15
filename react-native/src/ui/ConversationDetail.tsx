import React, {useState} from 'react';
import {ActivityIndicator, Image, Linking, Text, View} from 'react-native';
import {
  conversationDetailDateChipCopy,
  conversationDetailSpeakerCopy,
  conversationDisplaySummary,
  conversationDetailSummaryForStatusCopy,
  conversationDisplayTitle,
  processingConversationNoContentCopy,
  processingConversationDetailTitleCopy,
  processingConversationDetailContentTabCopy,
  conversationTranscriptDurationCopy,
  conversationDetailDurationCopy,
  conversationVisibilityCopy,
  conversationActionItemsTodoCopy,
  conversationActionItemsNoPendingCopy,
  conversationActionItemsCompletedCopy,
  conversationActionItemsNoCompletedCopy,
  conversationActionItemsEmptyCopy,
  conversationActionItemsEmptyDescriptionCopy,
  conversationNoFolderCopy,
  conversationCalendarAttendeesChipCopy,
  calendarEventDisplayTitle,
  legacyTranscriptCanDisplaySeconds,
  legacyTranscriptTimestampCopy,
  visibleDisplayText,
  type ConversationProjection,
  type TaskCardLookup,
  type GoalLinkLookup,
  type MemoryLinkLookup,
} from '../desktopReadClient';
import {RecordingTranscriptView} from './RecordingTranscript';
import {ChatConversationHistory} from './ChatConversationHistory';
import {desktopTokens} from '../desktop/tokens';
import {styles} from './styles';
import {FocusPressable} from './Pressable';
import {useLegacyConversationDetail} from '../useLegacyConversationDetail';
import {useRecordingTranscript} from '../recordingTranscript';

function CatalogAppImage({
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
      style={styles.cloudAppImage}
    />
  );
}

export function formatConversationDate(value: string | null): string {
  return conversationDetailDateChipCopy(value, Date.now());
}

function ConversationClockFields({
  conversation,
  ink,
  durationCopy,
  attendeesCopy,
  folderCopy,
  folderColor,
  folderIcon,
}: {
  conversation: ConversationProjection;
  ink?: {color: string};
  durationCopy?: string | null;
  attendeesCopy?: string | null;
  folderCopy?: string;
  folderColor?: string;
  folderIcon?: string;
}) {
  const visibilityCopy = conversationVisibilityCopy(conversation.visibility);
  const duration =
    durationCopy === undefined
      ? conversationDetailDurationCopy(conversation)
      : durationCopy;
  const folder = folderCopy ?? conversationNoFolderCopy();
  return (
    <View style={styles.conversationDetailFields}>
      <Text style={[styles.conversationDetailField, ink]}>
        {formatConversationDate(
          conversation.startedAt ?? conversation.createdAt,
        )}
      </Text>
      {duration !== null ? (
        <Text style={[styles.conversationDetailField, ink]}>{duration}</Text>
      ) : null}
      {attendeesCopy ? (
        <Text style={[styles.conversationDetailField, ink]}>
          {attendeesCopy}
        </Text>
      ) : null}
      <Text
        style={[
          styles.conversationDetailField,
          ink,
          folderColor ? {color: folderColor} : null,
        ]}>
        {folderIcon ? `${folderIcon} ` : null}
        {folder}
      </Text>
      {visibilityCopy === null ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {visibilityCopy}
        </Text>
      )}
    </View>
  );
}

function recordingSessionId(
  conversation: ConversationProjection,
): string | null {
  return conversation.source === 'omi' &&
    conversation.id.startsWith('recording:') &&
    conversation.id.length > 'recording:'.length
    ? conversation.id.slice('recording:'.length)
    : null;
}

function RecordingConversationFields({
  conversation,
  desktop,
  ink,
  sessionId,
}: {
  conversation: ConversationProjection;
  desktop: boolean;
  ink?: {color: string};
  sessionId: string;
}) {
  const {result, reload} = useRecordingTranscript(
    sessionId,
    conversation.updatedAt ?? undefined,
  );
  return (
    <>
      <ConversationClockFields
        conversation={conversation}
        ink={ink}
        durationCopy={
          result.status === 'loaded' && result.value.state === 'completed'
            ? conversationTranscriptDurationCopy(result.value.segments)
            : null
        }
      />
      <RecordingTranscriptView
        desktop={desktop}
        result={result}
        reload={reload}
      />
    </>
  );
}

export function ConversationDetail({
  conversation,
  desktop = false,
  apiContract,
  tasks,
  goals,
  memories,
}: {
  conversation: ConversationProjection;
  desktop?: boolean;
  apiContract?: 'omi';
  tasks?: readonly TaskCardLookup[];
  goals?: readonly GoalLinkLookup[];
  memories?: readonly MemoryLinkLookup[];
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
  const sessionId = recordingSessionId(conversation);
  return (
    <>
      <Text style={[styles.conversationDetailTitle, ink]}>
        {conversation.discarded
          ? 'Discarded Conversation'
          : conversationDisplayTitle(conversation)}
      </Text>
      {conversation.discarded ||
      conversationDisplaySummary(conversation) === '' ? null : (
        <Text style={[styles.conversationDetailSummary, ink]}>
          {conversationDisplaySummary(conversation)}
        </Text>
      )}
      {sessionId !== null ? (
        <RecordingConversationFields
          conversation={conversation}
          desktop={desktop}
          ink={ink}
          sessionId={sessionId}
        />
      ) : (
        <ConversationClockFields conversation={conversation} ink={ink} />
      )}
      {conversation.source === 'chat' &&
        conversation.id.startsWith('chat:') &&
        conversation.id.length > 'chat:'.length && (
          <ChatConversationHistory
            desktop={desktop}
            key={conversation.id}
            conversationId={conversation.id}
            tasks={tasks}
            goals={goals}
            memories={memories}
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
  const pendingActionItems = actionItems.filter(item => !item.completed);
  const completedActionItems = actionItems.filter(item => item.completed);
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
  const locationMapsUrl = conversation.discarded
    ? ''
    : visibleDisplayText(detail.locationMapsUrl ?? '');
  const appSummary = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummary ?? '');
  const appSummaryName = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummaryName ?? '');
  const appSummaryDescription = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummaryDescription ?? '');
  const appSummaryImageUri = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appSummaryImageUri ?? '');
  const appsError = conversation.discarded
    ? ''
    : visibleDisplayText(detail.appsError ?? '');
  const peopleError = visibleDisplayText(detail.peopleError ?? '');
  const calendarTitle = calendarEventDisplayTitle(detail.calendarEvent?.title);
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
  const calendarHtmlLink = visibleDisplayText(
    detail.calendarEvent?.htmlLink ?? '',
  );
  const calendarShareMailto = visibleDisplayText(
    detail.calendarEvent?.shareMailto ?? '',
  );
  const folderName = detail.folderName;
  const folderLabel =
    folderName === undefined || folderName === null
      ? conversationNoFolderCopy()
      : visibleDisplayText(folderName);
  const folderColor = visibleDisplayText(detail.folderColor ?? '');
  const folderIcon = visibleDisplayText(detail.folderIcon ?? '');
  const externalText = visibleDisplayText(detail.externalText ?? '');
  const detailSummaryCopy = conversation.discarded
    ? null
    : conversationDetailSummaryForStatusCopy(
        conversation.status,
        transcriptSegments.length === 0,
        {
          summary: detail.summary,
          sections: detail.sections,
          appSummary,
        },
      );
  const showExternalTranscript =
    externalText !== '' &&
    (detail.photoCount === undefined || detail.photoCount <= 0) &&
    (detail.transcript.status === 'unavailable' ||
      transcriptSegments.length === 0);
  const hasPhotos =
    (detail.photoCount ?? 0) > 0 ||
    (detail.photoRows ?? []).length > 0 ||
    (detail.photoCaptions ?? []).length > 0;
  const showProcessingEmptyContent =
    transcriptSegments.length === 0 &&
    !showExternalTranscript &&
    !hasPhotos &&
    (conversation.status === 'processing' || conversation.status === 'merging');
  return (
    <>
      <Text
        accessibilityRole="header"
        style={[styles.conversationDetailTitle, ink]}>
        {conversation.discarded
          ? 'Discarded Conversation'
          : conversation.status === 'processing' ||
              conversation.status === 'merging'
            ? processingConversationDetailTitleCopy()
            : conversationDisplayTitle({
                title: detail.title,
                status: conversation.status,
              })}
      </Text>
      {detailSummaryCopy === null ? null : (
        <Text selectable style={[styles.conversationDetailSummary, ink]}>
          {detailSummaryCopy}
        </Text>
      )}
      {appsError === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>{appsError}</Text>
      )}
      {appSummaryImageUri === '' ? null : (
        <CatalogAppImage
          accessibilityLabel={
            appSummaryName === '' ? 'App image' : appSummaryName
          }
          uri={appSummaryImageUri}
        />
      )}
      {appSummaryName === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {appSummaryName}
        </Text>
      )}
      {appSummaryDescription === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          {appSummaryDescription}
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
        durationCopy={
          detail.transcript.status === 'loaded'
            ? conversationTranscriptDurationCopy(detail.transcript.segments)
            : null
        }
        attendeesCopy={conversationCalendarAttendeesChipCopy(
          detail.calendarEvent?.attendees,
        )}
        folderCopy={folderLabel}
        folderColor={folderColor === '' ? undefined : folderColor}
        folderIcon={folderIcon === '' ? undefined : folderIcon}
      />
      {address === '' ? null : /^https?:\/\//i.test(locationMapsUrl) ? (
        <FocusPressable
          accessibilityRole="link"
          accessibilityLabel="Open in Maps"
          onPress={() => {
            Linking.openURL(locationMapsUrl).catch(() => undefined);
          }}>
          <Text style={[styles.conversationDetailField, ink]}>{address}</Text>
        </FocusPressable>
      ) : (
        <Text style={[styles.conversationDetailField, ink]}>{address}</Text>
      )}
      {detail.calendarEvent === undefined ? null : (
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
      {calendarHtmlLink === '' ? null : (
        <FocusPressable
          accessibilityRole="link"
          accessibilityLabel="Open in Google Calendar"
          onPress={() => {
            if (!/^https?:\/\//i.test(calendarHtmlLink)) {
              return;
            }
            Linking.openURL(calendarHtmlLink).catch(() => undefined);
          }}>
          <Text style={[styles.conversationDetailField, ink]}>
            Open in Google Calendar
          </Text>
        </FocusPressable>
      )}
      {calendarShareMailto === '' ? null : (
        <FocusPressable
          accessibilityRole="link"
          accessibilityLabel="Share with attendees"
          onPress={() => {
            if (!/^mailto:/i.test(calendarShareMailto)) {
              return;
            }
            Linking.openURL(calendarShareMailto).catch(() => undefined);
          }}>
          <Text style={[styles.conversationDetailField, ink]}>
            Share with attendees
          </Text>
        </FocusPressable>
      )}
      {(
        detail.photoRows ??
        (detail.photoCaptions ?? []).map(caption => ({caption}))
      ).flatMap((photo, index) => {
        const caption = visibleDisplayText(photo.caption ?? '');
        const imageUri = photo.imageUri;
        const nodes: React.JSX.Element[] = [];
        if (imageUri !== undefined && imageUri !== '') {
          nodes.push(
            <Image
              key={`photo-image-${index}`}
              accessibilityLabel={caption === '' ? 'Photo' : caption}
              source={{uri: imageUri}}
              style={styles.chatAttachmentImage}
            />,
          );
        }
        if (
          photo.unavailableCopy !== undefined &&
          photo.unavailableCopy !== ''
        ) {
          nodes.push(
            <Text
              key={`photo-unavailable-${index}`}
              accessibilityLabel={photo.unavailableCopy}
              style={[styles.conversationDetailField, ink]}>
              {photo.unavailableCopy}
            </Text>,
          );
        }
        if (caption !== '') {
          nodes.push(
            <Text
              key={`photo-caption-${index}`}
              style={[styles.conversationDetailField, ink]}>
              {caption}
            </Text>,
          );
        }
        return nodes;
      })}
      {conversation.discarded
        ? null
        : detail.sections.flatMap((section, index) => {
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
                  <Text
                    selectable
                    style={[styles.conversationTranscriptText, ink]}>
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
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            {conversationActionItemsTodoCopy()}
          </Text>
          <Text style={[styles.conversationDetailField, ink]}>
            {String(pendingActionItems.length)}
          </Text>
          {pendingActionItems.length > 0 ? (
            pendingActionItems.map((item, index) => (
              <View
                key={`pending-${index}`}
                style={styles.conversationDetailFields}>
                <Text
                  selectable
                  style={[styles.conversationTranscriptText, ink]}>
                  {item.description}
                </Text>
              </View>
            ))
          ) : (
            <Text style={[styles.conversationDetailField, ink]}>
              {conversationActionItemsNoPendingCopy()}
            </Text>
          )}
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            {conversationActionItemsCompletedCopy()}
          </Text>
          <Text style={[styles.conversationDetailField, ink]}>
            {String(completedActionItems.length)}
          </Text>
          {completedActionItems.length > 0 ? (
            completedActionItems.map((item, index) => (
              <View
                key={`completed-${index}`}
                style={styles.conversationDetailFields}>
                <Text
                  selectable
                  style={[styles.conversationTranscriptText, ink]}>
                  {item.description}
                </Text>
              </View>
            ))
          ) : (
            <Text style={[styles.conversationDetailField, ink]}>
              {conversationActionItemsNoCompletedCopy()}
            </Text>
          )}
        </>
      ) : (
        <>
          <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
            {conversationActionItemsEmptyCopy()}
          </Text>
          <Text style={[styles.conversationDetailField, ink]}>
            {conversationActionItemsEmptyDescriptionCopy()}
          </Text>
        </>
      )}
      <Text accessibilityRole="header" style={[styles.resultTitle, ink]}>
        {conversation.status === 'processing' ||
        conversation.status === 'merging'
          ? processingConversationDetailContentTabCopy(conversation.source)
          : 'Transcript'}
      </Text>
      {peopleError === '' ? null : (
        <Text style={[styles.conversationDetailField, ink]}>
          People
          {': '}
          {peopleError}
        </Text>
      )}
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
      ) : showProcessingEmptyContent ? (
        <Text style={[styles.conversationDetailSummary, ink]}>
          {processingConversationNoContentCopy()}
        </Text>
      ) : transcriptSegments.length === 0 ? null : (
        transcriptSegments.map((segment, index) => {
          const speaker = conversationDetailSpeakerCopy(
            segment,
            transcriptSegments,
          );
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
              {segment.sttProvider !== undefined ? (
                <Text style={[styles.conversationDetailField, ink]}>
                  {segment.sttProvider}
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
