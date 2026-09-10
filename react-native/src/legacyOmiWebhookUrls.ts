import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

export const OMI_WEBHOOK_URL_TYPES = [
  'memory_created',
  'realtime_transcript',
  'audio_bytes',
  'day_summary',
] as const;

export type OmiWebhookUrlType = (typeof OMI_WEBHOOK_URL_TYPES)[number];

export type OmiWebhookUrl = {
  url: string | null;
  intervalSeconds: string | null;
};

class WebhookUrlError extends Error {
  constructor() {
    super('Omi webhook URL is malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new WebhookUrlError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new WebhookUrlError();
  }
  return value;
}

export function parseOmiWebhookUrl(
  body: string,
  type: OmiWebhookUrlType,
): OmiWebhookUrl | null {
  const row = object(JSON.parse(body));
  const raw = visibleDisplayText(text(row.url, 2048));
  if (raw === '') {
    return null;
  }
  if (type !== 'audio_bytes') {
    return {url: raw, intervalSeconds: null};
  }
  const comma = raw.indexOf(',');
  if (comma < 0) {
    return {url: raw, intervalSeconds: null};
  }
  const url = visibleDisplayText(raw.slice(0, comma));
  const interval = visibleDisplayText(raw.slice(comma + 1));
  const intervalSeconds = /^[0-9]+$/.test(interval) ? interval : null;
  if (url === '' && intervalSeconds === null) {
    return null;
  }
  return {
    url: url === '' ? null : url,
    intervalSeconds,
  };
}

async function loadOmiWebhookUrl(
  backend: OmiBackend,
  type: OmiWebhookUrlType,
): Promise<[OmiWebhookUrlType, OmiWebhookUrl] | null> {
  const response = await backend.request({
    id: 'omi-webhook-url',
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/users/developer/webhook/${encodeURIComponent(type)}`,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    const parsed = parseOmiWebhookUrl(response.body, type);
    return parsed === null ? null : [type, parsed];
  } catch {
    return null;
  }
}

export async function loadOmiWebhookUrls(
  backend: OmiBackend,
): Promise<Map<OmiWebhookUrlType, OmiWebhookUrl>> {
  const rows = await Promise.all(
    OMI_WEBHOOK_URL_TYPES.map(type => loadOmiWebhookUrl(backend, type)),
  );
  const urls = new Map<OmiWebhookUrlType, OmiWebhookUrl>();
  for (const row of rows) {
    if (row !== null) {
      urls.set(row[0], row[1]);
    }
  }
  return urls;
}

export function mergeWebhookUrl(
  webhook: {type: string; enabled: boolean | null; url: string | null},
  urls: ReadonlyMap<string, OmiWebhookUrl>,
): {
  enabled: boolean | null;
  url: string | null;
  intervalSeconds: string | null;
} {
  const extra = urls.get(webhook.type);
  if (extra === undefined) {
    return {
      enabled: webhook.enabled,
      url: webhook.url,
      intervalSeconds: null,
    };
  }
  return {
    enabled: webhook.enabled,
    url: extra.url,
    intervalSeconds: extra.intervalSeconds,
  };
}
