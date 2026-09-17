import type {NativeHttpResponse, OmiBackend} from './omiNativeTypes';
import {isOptionalCaptureTimestamp} from './captureTimestamp';
import type {TimelineRecall} from './timeline/mixedTimeline';

export type RewindMomentRecord = {
  frameId: string;
  capturedAtMs: number;
  appName: string;
  windowTitle: string;
  source: 'captured' | 'shipping';
  ocrPreview: string;
};

export type RewindMomentPage = {
  items: RewindMomentRecord[];
  hasMore: boolean;
  nextCursor: string | null;
};

export class RewindMomentBackendError extends Error {
  constructor(readonly status: number, readonly backendCode: string) {
    super(`Rewind moment backend failed (${status}:${backendCode})`);
  }
}

function parseObject(body: string | null): Record<string, unknown> {
  if (body === null) {
    throw new Error('Backend returned an empty response');
  }
  const value: unknown = JSON.parse(body);
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Backend returned a non-object response');
  }
  return value as Record<string, unknown>;
}

function parseMoment(value: unknown): RewindMomentRecord {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Backend returned a non-object moment');
  }
  const item = value as Record<string, unknown>;
  if (
    typeof item.frameId !== 'string' ||
    typeof item.appName !== 'string' ||
    typeof item.windowTitle !== 'string' ||
    (item.source !== 'captured' && item.source !== 'shipping') ||
    typeof item.ocrPreview !== 'string' ||
    !isOptionalCaptureTimestamp(item.capturedAtMs) ||
    item.capturedAtMs === undefined
  ) {
    throw new Error('Rewind moment response is incomplete');
  }
  if ('base64' in item || 'jpegBase64' in item || 'image' in item) {
    throw new Error('Rewind moment response invented pixel bytes');
  }
  return {
    frameId: item.frameId,
    capturedAtMs: item.capturedAtMs,
    appName: item.appName,
    windowTitle: item.windowTitle,
    source: item.source,
    ocrPreview: item.ocrPreview,
  };
}

function rejectHttp(response: NativeHttpResponse): never {
  let code = 'unknown';
  try {
    const body = parseObject(response.body);
    const error = body.error;
    if (
      error !== null &&
      typeof error === 'object' &&
      !Array.isArray(error) &&
      typeof (error as {code?: unknown}).code === 'string'
    ) {
      code = (error as {code: string}).code;
    }
  } catch {
    code = 'unknown';
  }
  throw new RewindMomentBackendError(response.status, code);
}

export async function upsertRewindMoment(
  backend: OmiBackend,
  moment: RewindMomentRecord,
): Promise<RewindMomentRecord> {
  const response = await backend.request({
    id: 'rewind-moment-upsert',
    method: 'POST',
    path: '/v1/rewind-moments',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify(moment),
  });
  if (response.status < 200 || response.status >= 300) {
    rejectHttp(response);
  }
  return parseMoment(parseObject(response.body).moment);
}

export async function loadRewindMoments(
  backend: OmiBackend,
  cursor: string | null = null,
): Promise<RewindMomentPage> {
  const path =
    cursor === null
      ? '/v1/rewind-moments?limit=50'
      : `/v1/rewind-moments?limit=50&cursor=${encodeURIComponent(cursor)}`;
  const response = await backend.request({
    id: 'rewind-moments-read',
    method: 'GET',
    path: path as `/${string}`,
  });
  if (response.status < 200 || response.status >= 300) {
    rejectHttp(response);
  }
  const body = parseObject(response.body);
  if (!Array.isArray(body.items)) {
    throw new Error('Rewind moment page is incomplete');
  }
  const window = body.window;
  const hasMore =
    window !== null &&
    typeof window === 'object' &&
    !Array.isArray(window) &&
    (window as {hasMore?: unknown}).hasMore === true;
  const nextCursor =
    window !== null &&
    typeof window === 'object' &&
    !Array.isArray(window) &&
    typeof (window as {nextCursor?: unknown}).nextCursor === 'string'
      ? ((window as {nextCursor: string}).nextCursor)
      : null;
  return {
    items: body.items.map(parseMoment),
    hasMore,
    nextCursor,
  };
}

export function recallFromMoment(moment: RewindMomentRecord): TimelineRecall {
  return {
    kind: 'recall',
    id: moment.frameId,
    appName: moment.appName,
    windowTitle: moment.windowTitle,
    searchableText: `${moment.appName} ${moment.windowTitle} ${moment.ocrPreview}`,
    atMs: moment.capturedAtMs,
    source: 'backend',
    local: false,
  };
}
