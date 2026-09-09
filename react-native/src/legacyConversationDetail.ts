import type {OmiBackend} from './omiNativeTypes';

export type LegacyConversationDetail = {
  id: string;
  title: string;
  summary: string;
  locked: boolean;
  sections: {heading: string; bodyMarkdown: string}[];
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
  // Old list responses omit transcripts; even detail can redact locked data.
  // Only an explicit unlocked array establishes an empty or loaded transcript.
  const transcript: LegacyConversationDetail['transcript'] =
    locked || value.transcript_segments == null
      ? {status: 'unavailable'}
      : {
          status: 'loaded',
          segments: array(value.transcript_segments, 20000).map(raw => {
            const segment = object(raw);
            return {
              text: text(segment.text, 100000),
              speaker:
                segment.speaker == null ? null : text(segment.speaker, 256),
              isUser: boolean(segment.is_user),
              start: finite(segment.start),
              end: finite(segment.end),
            };
          }),
        };
  return {
    id,
    title: text(structured.title),
    summary: text(structured.overview),
    locked,
    sections,
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
