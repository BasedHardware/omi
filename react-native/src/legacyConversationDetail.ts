import type {OmiBackend} from './omiNativeTypes';
import {
  conversationPhotoChrome,
  conversationPhotoDataUri,
  conversationPhotoUnavailableCopy,
  conversationFirstPartySummaryCopy,
  conversationNoFolderCopy,
  conversationUnknownAppCopy,
  conversationLocationAddressCopy,
  desktopReadErrorCopy,
  transcriptSttProviderCopy,
  calendarEventDisplayTitle,
  visibleDisplayText,
} from './desktopReadClient';
import {loadOmiFolder} from './legacyOmiFolders';
import {loadOmiPeopleNames} from './legacyOmiPeople';
import {loadOmiApps, type OmiAppChrome} from './legacyOmiApps';

export type LegacyConversationDetail = {
  id: string;
  title: string;
  summary: string;
  locked: boolean;
  sections: {heading: string; bodyMarkdown: string}[];
  actionItems: {description: string; completed: boolean}[];
  locationAddress?: string;
  locationMapsUrl?: string;
  appSummary?: string;
  appSummaryName?: string;
  appSummaryDescription?: string;
  appSummaryImageUri?: string;
  calendarEvent?: {
    title: string;
    attendees: string[];
    startCopy?: string;
    endCopy?: string;
    htmlLink?: string;
    shareMailto?: string;
  };
  photoCount?: number;
  photoCaptions?: string[];
  photoRows?: {caption?: string; imageUri?: string; unavailableCopy?: string}[];
  folderName?: string;
  folderColor?: string;
  folderIcon?: string;
  peopleError?: string;
  appsError?: string;
  externalText?: string;
  transcript:
    | {status: 'unavailable'}
    | {
        status: 'loaded';
        segments: {
          text: string;
          speaker: string | null;
          isUser: boolean;
          start: number;
          end: number;
          personName?: string;
          translations?: string[];
          sttProvider?: string;
        }[];
      };
};

class DetailError extends Error {
  constructor(readonly kind: 'auth' | 'changed' | 'missing' | 'invalid') {
    super('Conversation detail unavailable');
  }
}
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new DetailError('invalid');
  }
  return value as Record<string, unknown>;
}
function text(value: unknown, limit = 6 * 1024 * 1024): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new DetailError('invalid');
  }
  return value;
}
function omittedText(value: unknown, limit = 6 * 1024 * 1024): string {
  if (value === undefined || value === null) {
    return '';
  }
  return text(value, limit);
}
function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new DetailError('invalid');
  }
  return value;
}
function finite(value: unknown): number {
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (value.trim() === '' || !Number.isFinite(parsed)) {
      throw new DetailError('invalid');
    }
    return parsed;
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new DetailError('invalid');
  }
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new DetailError('invalid');
  }
  return value;
}
function optionalObjectRows(value: unknown): unknown[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new DetailError('invalid');
  }
  return value;
}
function optionalArray(value: unknown): unknown[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    return [];
  }
  return value;
}
function appResultId(row: Record<string, unknown>): {
  appId?: string;
  unusable?: true;
} {
  const raw = row.plugin_id ?? row.app_id;
  if (raw === undefined || raw === null) {
    return {};
  }
  if (typeof raw !== 'string') {
    return {unusable: true};
  }
  const id = visibleDisplayText(raw);
  return id === '' ? {} : {appId: id};
}

function firstPartySummaryChrome(
  overview: string,
  sections: LegacyConversationDetail['sections'],
): boolean {
  if (visibleDisplayText(overview) !== '') {
    return true;
  }
  return sections.some(
    section =>
      visibleDisplayText(section.heading) !== '' ||
      visibleDisplayText(section.bodyMarkdown) !== '',
  );
}

function appSummaryAttribution(recap: {
  resolvedName: string;
  appId?: string;
  appsError?: string;
  unusable?: true;
  hasRecap: boolean;
  hasFirstPartyChrome: boolean;
}): string | undefined {
  if (recap.resolvedName !== '') {
    return recap.resolvedName;
  }
  if (recap.appId !== undefined) {
    return recap.appsError === undefined
      ? conversationUnknownAppCopy()
      : undefined;
  }
  if (recap.unusable === true) {
    return undefined;
  }
  return recap.hasRecap || recap.hasFirstPartyChrome
    ? conversationFirstPartySummaryCopy()
    : undefined;
}

function firstAppSummary(
  apps: unknown,
  plugins: unknown,
  overview: string,
): {content: string; appId?: string; unusable?: true} | undefined {
  const appRows = optionalObjectRows(apps);
  const rows =
    appRows.length > 0 ? appRows : optionalObjectRows(plugins);
  for (const raw of rows) {
    const row = object(raw);
    const content = visibleDisplayText(text(row.content));
    if (content !== '' && content !== overview) {
      const id = appResultId(row);
      return {
        content,
        ...(id.appId === undefined ? {} : {appId: id.appId}),
        ...(id.unusable === true ? {unusable: true} : {}),
      };
    }
  }
  return undefined;
}
function locationChrome(value: unknown): {
  locationAddress?: string;
  locationMapsUrl?: string;
} {
  if (value === undefined || value === null) {
    return {};
  }
  const geo = object(value);
  const latitude = finite(geo.latitude);
  const longitude = finite(geo.longitude);
  const address =
    geo.address === undefined || geo.address === null
      ? ''
      : text(geo.address);
  return {
    locationAddress: conversationLocationAddressCopy(address),
    locationMapsUrl: `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`,
  };
}
function externalText(value: unknown): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const data = object(value);
  if (data.text === undefined || data.text === null) {
    return undefined;
  }
  const copy = visibleDisplayText(text(data.text));
  return copy === '' ? undefined : copy;
}
function calendarEventTimeCopy(value: unknown): string {
  const parsed = Date.parse(text(value).replace(/([+-]\d{2})$/, '$1:00'));
  if (!Number.isFinite(parsed)) {
    throw new DetailError('invalid');
  }
  return visibleDisplayText(
    new Date(parsed).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    }),
  );
}
function calendarEvent(
  value: unknown,
): LegacyConversationDetail['calendarEvent'] {
  if (value === undefined || value === null) {
    return undefined;
  }
  const event = object(value);
  text(event.event_id, 1_000_000);
  const title = calendarEventDisplayTitle(text(event.title));
  const startCopy = calendarEventTimeCopy(event.start_time);
  const endCopy = calendarEventTimeCopy(event.end_time);
  if (
    event.attendees !== undefined &&
    event.attendees !== null &&
    !Array.isArray(event.attendees)
  ) {
    throw new DetailError('invalid');
  }
  const attendees = (
    Array.isArray(event.attendees) ? event.attendees : []
  ).map(raw => visibleDisplayText(text(raw)));
  if (
    event.attendee_emails !== undefined &&
    event.attendee_emails !== null &&
    !Array.isArray(event.attendee_emails)
  ) {
    throw new DetailError('invalid');
  }
  const attendeeEmails = (
    Array.isArray(event.attendee_emails) ? event.attendee_emails : []
  ).flatMap(raw => {
    const email = visibleDisplayText(text(raw));
    return email === '' ? [] : [email];
  });
  const htmlLink =
    event.html_link === undefined || event.html_link === null
      ? undefined
      : visibleDisplayText(text(event.html_link));
  const shareMailto =
    attendeeEmails.length === 0
      ? ''
      : `mailto:${attendeeEmails.join(',')}?subject=${encodeURIComponent(
          `Notes: ${title}`,
        )}`;
  if (
    title === '' &&
    attendees.length === 0 &&
    startCopy === '' &&
    endCopy === ''
  ) {
    return undefined;
  }
  return {
    title,
    attendees,
    ...(startCopy === '' ? {} : {startCopy}),
    ...(endCopy === '' ? {} : {endCopy}),
    ...(htmlLink === undefined ? {} : {htmlLink}),
    ...(shareMailto === '' ? {} : {shareMailto}),
  };
}
function segmentTranslations(value: unknown): string[] | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!Array.isArray(value)) {
    throw new DetailError('invalid');
  }
  const translations: string[] = [];
  for (const raw of value) {
    const row = object(raw);
    text(row.lang);
    const copy = visibleDisplayText(text(row.text));
    if (copy !== '') {
      translations.push(copy);
    }
  }
  return translations.length === 0 ? undefined : translations;
}

function conversationPhotos(value: unknown):
  | {
      count: number;
      captions: string[];
      rows: {caption?: string; imageUri?: string; unavailableCopy?: string}[];
    }
  | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!Array.isArray(value)) {
    throw new DetailError('invalid');
  }
  const rows = value;
  if (rows.length === 0) {
    return undefined;
  }
  const items = rows.map(raw => {
    const photo = object(raw);
    const discarded =
      photo.discarded === undefined || photo.discarded === null
        ? false
        : boolean(photo.discarded);
    const caption =
      photo.description === undefined || photo.description === null
        ? conversationPhotoChrome({discarded})
        : conversationPhotoChrome({
            discarded,
            description: text(photo.description),
          });
    if (photo.base64 === undefined || photo.base64 === null) {
      throw new DetailError('invalid');
    }
    const imageUri = conversationPhotoDataUri(
      text(photo.base64, 20_000_000),
      photo.content_type === undefined || photo.content_type === null
        ? undefined
        : text(photo.content_type),
    );
    const storageId =
      photo.storage_id === undefined || photo.storage_id === null
        ? ''
        : visibleDisplayText(text(photo.storage_id));
    const unavailableCopy =
      imageUri !== undefined || (photo.base64 === '' && storageId !== '')
        ? undefined
        : conversationPhotoUnavailableCopy();
    return {
      ...(caption === undefined ? {} : {caption}),
      ...(imageUri === undefined ? {} : {imageUri}),
      ...(unavailableCopy === undefined ? {} : {unavailableCopy}),
    };
  });
  return {
    count: rows.length,
    captions: items.flatMap(item =>
      item.caption === undefined ? [] : [item.caption],
    ),
    rows: items,
  };
}

export async function loadLegacyConversationDetail(
  backend: OmiBackend,
  id: string,
  signal?: AbortSignal,
): Promise<LegacyConversationDetail> {
  if (
    !id ||
    id.length > 1_000_000 ||
    [...id].some(character => character.charCodeAt(0) < 32)
  ) {
    throw new DetailError('invalid');
  }
  if (signal?.aborted) {
    throw new DetailError('invalid');
  }
  if ((await backend.getApiContract?.()) !== 'omi') {
    throw new DetailError('changed');
  }
  if (signal?.aborted) {
    throw new DetailError('invalid');
  }
  const response = await backend.request({
    id: `omi-conversation-detail:${id}`,
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/conversations/${encodeURIComponent(id)}`,
  });
  if (signal?.aborted) {
    throw new DetailError('invalid');
  }
  if (response.status === 401) {
    throw new DetailError('auth');
  }
  if (response.status === 404) {
    throw new DetailError('missing');
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 6 * 1024 * 1024
  ) {
    throw new DetailError('invalid');
  }
  const value = object(JSON.parse(response.body));
  if (value.id !== id) {
    throw new DetailError('invalid');
  }
  const structured = object(value.structured);
  const locked = boolean(value.is_locked ?? false);
  const sections: LegacyConversationDetail['sections'] = [];
  for (const raw of optionalArray(structured.sections)) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      continue;
    }
    const section = raw as Record<string, unknown>;
    if (
      typeof section.heading !== 'string' ||
      typeof section.body_markdown !== 'string'
    ) {
      continue;
    }
    sections.push({
      heading: text(section.heading),
      bodyMarkdown: text(section.body_markdown),
    });
  }
  const actionItems: LegacyConversationDetail['actionItems'] = [];
  for (const raw of optionalArray(
    structured.action_items ?? structured.actionItems,
  )) {
    if (typeof raw === 'string') {
      if (raw === '') {
        continue;
      }
      actionItems.push({description: text(raw), completed: false});
      continue;
    }
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      continue;
    }
    const item = raw as Record<string, unknown>;
    if (item.deleted !== undefined) {
      if (typeof item.deleted !== 'boolean') {
        continue;
      }
      if (item.deleted) {
        continue;
      }
    }
    if (typeof item.description !== 'string') {
      continue;
    }
    if (item.completed !== undefined && typeof item.completed !== 'boolean') {
      continue;
    }
    actionItems.push({
      description: text(item.description),
      completed: item.completed === undefined ? false : item.completed,
    });
  }
  // Old list responses omit transcripts; even detail can redact locked data.
  // Only an explicit unlocked array establishes an empty or loaded transcript.
  let peopleError: string | undefined;
  const transcript: LegacyConversationDetail['transcript'] =
    locked || value.transcript_segments == null
      ? {status: 'unavailable'}
      : {
          status: 'loaded',
          segments: await (async () => {
            const segments = array(value.transcript_segments).map(
              raw => {
                const segment = object(raw);
                const personId =
                  segment.person_id === undefined || segment.person_id === null
                    ? undefined
                    : visibleDisplayText(text(segment.person_id, 1_000_000));
                const translations = segmentTranslations(segment.translations);
                const sttProvider =
                  segment.stt_provider === undefined ||
                  segment.stt_provider === null
                    ? undefined
                    : transcriptSttProviderCopy(text(segment.stt_provider));
                return {
                  text: text(segment.text),
                  speaker:
                    segment.speaker == null
                      ? 'SPEAKER_00'
                      : text(segment.speaker),
                  isUser: boolean(segment.is_user),
                  start: finite(segment.start),
                  end: finite(segment.end),
                  ...(personId === undefined || personId === ''
                    ? {}
                    : {personId}),
                  ...(translations === undefined ? {} : {translations}),
                  ...(sttProvider === undefined ? {} : {sttProvider}),
                };
              },
            );
            const needsPeople = segments.some(
              segment => segment.personId !== undefined,
            );
            const names = needsPeople
              ? await loadOmiPeopleNames(backend, signal).then(
                  value => value ?? new Map<string, string>(),
                  reason => {
                    peopleError = desktopReadErrorCopy(reason);
                    return new Map<string, string>();
                  },
                )
              : new Map<string, string>();
            return segments.map(segment => {
              const {personId, ...rest} = segment;
              const personName =
                personId === undefined ? undefined : names.get(personId);
              return {
                ...rest,
                ...(personName === undefined || personName === ''
                  ? {}
                  : {personName}),
              };
            });
          })(),
        };
  const location = locationChrome(value.geolocation);
  const linkedEvent = calendarEvent(value.calendar_event);
  const photos = conversationPhotos(value.photos);
  const integrationText = externalText(value.external_data);
  const overview = omittedText(structured.overview);
  const appRecap = firstAppSummary(
    value.apps_results,
    value.plugins_results,
    visibleDisplayText(overview),
  );
  const appSummary = appRecap?.content;
  let appsError: string | undefined;
  const appChrome =
    appRecap?.appId === undefined
      ? undefined
      : (
          await loadOmiApps(backend, [appRecap.appId]).then(
            map => map,
            reason => {
              appsError = desktopReadErrorCopy(reason);
              return new Map<string, OmiAppChrome>();
            },
          )
        ).get(appRecap.appId);
  const resolvedAppName =
    appChrome === undefined
      ? undefined
      : visibleDisplayText(appChrome.name);
  const appSummaryName =
    resolvedAppName === undefined
      ? appSummaryAttribution({
          resolvedName: '',
          appId: appRecap?.appId,
          appsError,
          unusable: appRecap?.unusable,
          hasRecap: appRecap !== undefined,
          hasFirstPartyChrome: firstPartySummaryChrome(overview, sections),
        })
      : resolvedAppName;
  const appSummaryDescription = appChrome?.description;
  const appSummaryImageUri = appChrome?.image;
  const folderId =
    value.folder_id === undefined || value.folder_id === null
      ? undefined
      : visibleDisplayText(text(value.folder_id, 1_000_000));
  const folder =
    folderId === undefined || folderId === ''
      ? undefined
      : await loadOmiFolder(backend, folderId, signal).catch(() => undefined);
  return {
    id,
    title: omittedText(structured.title),
    summary: overview,
    locked,
    sections,
    actionItems,
    ...(location.locationAddress === undefined
      ? {}
      : {locationAddress: location.locationAddress}),
    ...(location.locationMapsUrl === undefined
      ? {}
      : {locationMapsUrl: location.locationMapsUrl}),
    ...(appSummary === undefined ? {} : {appSummary}),
    ...(appSummaryName === undefined ? {} : {appSummaryName}),
    ...(appSummaryDescription === undefined
      ? {}
      : {appSummaryDescription}),
    ...(appSummaryImageUri === undefined || appSummaryImageUri === ''
      ? {}
      : {appSummaryImageUri}),
    ...(peopleError === undefined ? {} : {peopleError}),
    ...(appsError === undefined ? {} : {appsError}),
    ...(linkedEvent === undefined ? {} : {calendarEvent: linkedEvent}),
    ...(photos === undefined
      ? {}
      : {
          photoCount: photos.count,
          ...(photos.captions.length === 0
            ? {}
            : {photoCaptions: photos.captions}),
          photoRows: photos.rows,
        }),
    ...(folder === undefined
      ? {folderName: conversationNoFolderCopy()}
      : {
          folderName: folder.name,
          ...(folder.color === undefined ? {} : {folderColor: folder.color}),
          ...(folder.icon === undefined ? {} : {folderIcon: folder.icon}),
        }),
    ...(integrationText === undefined ? {} : {externalText: integrationText}),
    transcript,
  };
}

export function legacyConversationDetailErrorCopy(error: unknown): string {
  const code = (error as {code?: unknown} | null)?.code;
  if (
    (error instanceof DetailError && error.kind === 'auth') ||
    code === 'OMI_HTTP_UNAUTHORIZED'
  ) {
    return 'Sign in again to read this conversation.';
  }
  if (
    (error instanceof DetailError && error.kind === 'changed') ||
    code === 'OMI_HTTP_BACKEND_CHANGED'
  ) {
    return 'The selected backend changed. Reopen this conversation.';
  }
  if (error instanceof DetailError && error.kind === 'missing') {
    return 'This conversation is no longer available.';
  }
  return 'Conversation details could not be loaded. Try again.';
}
