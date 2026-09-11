import type {OmiBackend} from './omiNativeTypes';
import {
  conversationPhotoChrome,
  conversationPhotoDataUri,
  desktopReadErrorCopy,
  transcriptSttProviderCopy,
  visibleDisplayText,
} from './desktopReadClient';
import {loadOmiFolderName} from './legacyOmiFolders';
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
  appSummary?: string;
  appSummaryName?: string;
  appSummaryDescription?: string;
  calendarEvent?: {
    title?: string;
    attendees: string[];
    startCopy?: string;
    endCopy?: string;
  };
  photoCount?: number;
  photoCaptions?: string[];
  photoRows?: {caption?: string; imageUri?: string}[];
  folderName?: string;
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
function text(value: unknown, limit = 1000000): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new DetailError('invalid');
  }
  return value;
}
function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new DetailError('invalid');
  }
  return value;
}
function finite(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new DetailError('invalid');
  }
  return value;
}
function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new DetailError('invalid');
  }
  return value;
}
function appResultId(row: Record<string, unknown>): string | undefined {
  const raw = row.plugin_id ?? row.app_id;
  if (typeof raw !== 'string') {
    return undefined;
  }
  const id = visibleDisplayText(raw);
  return id === '' ? undefined : id;
}

function firstAppSummary(
  apps: unknown,
  plugins: unknown,
  overview: string,
): {content: string; appId?: string} | undefined {
  const appRows = apps === undefined || apps === null ? [] : array(apps, 1000);
  const rows =
    appRows.length > 0
      ? appRows
      : plugins === undefined || plugins === null
      ? []
      : array(plugins, 1000);
  for (const raw of rows) {
    const row = object(raw);
    const content = visibleDisplayText(text(row.content, 100000));
    if (content !== '' && content !== overview) {
      const appId = appResultId(row);
      return appId === undefined ? {content} : {content, appId};
    }
  }
  return undefined;
}
function locationAddress(value: unknown): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const geo = object(value);
  if (geo.address === undefined || geo.address === null) {
    return undefined;
  }
  const address = visibleDisplayText(text(geo.address, 10000));
  return address === '' ? undefined : address;
}
function externalText(value: unknown): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const data = object(value);
  if (data.text === undefined || data.text === null) {
    return undefined;
  }
  const copy = visibleDisplayText(text(data.text, 100000));
  return copy === '' ? undefined : copy;
}
function calendarEventTimeCopy(value: unknown): string {
  const parsed = Date.parse(text(value, 100));
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
  text(event.event_id, 10000);
  const title = visibleDisplayText(text(event.title, 10000));
  const startCopy = calendarEventTimeCopy(event.start_time);
  const endCopy = calendarEventTimeCopy(event.end_time);
  const attendees = array(event.attendees ?? [], 1000).flatMap(raw => {
    const name = visibleDisplayText(text(raw, 10000));
    return name === '' ? [] : [name];
  });
  if (
    title === '' &&
    attendees.length === 0 &&
    startCopy === '' &&
    endCopy === ''
  ) {
    return undefined;
  }
  return {
    ...(title === '' ? {} : {title}),
    attendees,
    ...(startCopy === '' ? {} : {startCopy}),
    ...(endCopy === '' ? {} : {endCopy}),
  };
}
function segmentTranslations(value: unknown): string[] | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const rows = array(value, 32);
  const translations: string[] = [];
  for (const raw of rows) {
    const row = object(raw);
    text(row.lang, 32);
    const copy = visibleDisplayText(text(row.text, 100000));
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
      rows: {caption?: string; imageUri?: string}[];
    }
  | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const rows = array(value, 1000);
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
            description: text(photo.description, 10000),
          });
    const imageUri =
      photo.base64 === undefined || photo.base64 === null
        ? undefined
        : conversationPhotoDataUri(
            text(photo.base64, 20_000_000),
            photo.content_type === undefined || photo.content_type === null
              ? undefined
              : text(photo.content_type, 256),
          );
    return {
      ...(caption === undefined ? {} : {caption}),
      ...(imageUri === undefined ? {} : {imageUri}),
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
    id.length > 256 ||
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
  const sections = array(structured.sections ?? [], 1000).map(raw => {
    const section = object(raw);
    return {
      heading: text(section.heading, 10000),
      bodyMarkdown: text(section.body_markdown),
    };
  });
  const actionItems = array(
    structured.action_items ?? structured.actionItems ?? [],
    1000,
  ).flatMap(raw => {
    if (typeof raw === 'string') {
      return [{description: raw, completed: false}];
    }
    const item = object(raw);
    if (item.deleted === undefined ? false : boolean(item.deleted)) {
      return [];
    }
    return [
      {
        description: text(item.description, 10000),
        completed:
          item.completed === undefined ? false : boolean(item.completed),
      },
    ];
  });
  // Old list responses omit transcripts; even detail can redact locked data.
  // Only an explicit unlocked array establishes an empty or loaded transcript.
  let peopleError: string | undefined;
  const transcript: LegacyConversationDetail['transcript'] =
    locked || value.transcript_segments == null
      ? {status: 'unavailable'}
      : {
          status: 'loaded',
          segments: await (async () => {
            const segments = array(value.transcript_segments, 20000).map(
              raw => {
                const segment = object(raw);
                const personId =
                  segment.person_id === undefined || segment.person_id === null
                    ? undefined
                    : visibleDisplayText(text(segment.person_id, 256));
                const translations = segmentTranslations(segment.translations);
                const sttProvider =
                  segment.stt_provider === undefined ||
                  segment.stt_provider === null
                    ? undefined
                    : transcriptSttProviderCopy(
                        text(segment.stt_provider, 256),
                      );
                return {
                  text: text(segment.text, 100000),
                  speaker:
                    segment.speaker == null ? null : text(segment.speaker, 256),
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
                  value => value,
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
  const address = locationAddress(value.geolocation);
  const linkedEvent = calendarEvent(value.calendar_event);
  const photos = conversationPhotos(value.photos);
  const integrationText = externalText(value.external_data);
  const overview = text(structured.overview);
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
  const appSummaryName = appChrome?.name;
  const appSummaryDescription = appChrome?.description;
  const folderId =
    value.folder_id === undefined || value.folder_id === null
      ? undefined
      : visibleDisplayText(text(value.folder_id, 256));
  const folderName =
    folderId === undefined || folderId === ''
      ? undefined
      : await loadOmiFolderName(backend, folderId, signal).catch(
          () => undefined,
        );
  return {
    id,
    title: text(structured.title),
    summary: overview,
    locked,
    sections,
    actionItems,
    ...(address === undefined ? {} : {locationAddress: address}),
    ...(appSummary === undefined ? {} : {appSummary}),
    ...(appSummaryName === undefined || appSummaryName === ''
      ? {}
      : {appSummaryName}),
    ...(appSummaryDescription === undefined || appSummaryDescription === ''
      ? {}
      : {appSummaryDescription}),
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
    ...(folderName === undefined ? {} : {folderName}),
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
