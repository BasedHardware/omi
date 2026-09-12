import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class CaptureGapError extends Error {
  constructor() {
    super('Omi calendar capture gaps are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new CaptureGapError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new CaptureGapError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new CaptureGapError();
  }
  return value;
}

function timestampMs(value: unknown): number {
  const parsed = Date.parse(text(value, 100));
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new CaptureGapError();
  }
  return parsed;
}

function optionalText(value: unknown): void {
  if (value === undefined) {
    return;
  }
  text(value, 10000);
}

export type OmiCalendarCaptureGap = {
  eventId: string;
  title: string;
  startMs: number;
  endMs: number;
};

export function captureGapTimeCopy(timestampMs: number): string {
  if (!Number.isFinite(timestampMs) || timestampMs <= 0) {
    return '';
  }
  return visibleDisplayText(
    new Date(timestampMs).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    }),
  );
}

export function captureGapTimeRangeCopy(
  startMs: number,
  endMs: number,
): string {
  const start = captureGapTimeCopy(startMs);
  const end = captureGapTimeCopy(endMs);
  if (start === '') {
    return end;
  }
  if (end === '') {
    return start;
  }
  return `${start} – ${end}`;
}

export function captureGapHeaderCopy(count: number): string {
  if (!Number.isInteger(count) || count <= 0) {
    return '';
  }
  return `Not captured (${count})`;
}

export function calendarCaptureGapSpan(
  items: readonly {startedAt: string | null; createdAt: string}[],
): {start: string; end: string} | null {
  let oldest = Number.POSITIVE_INFINITY;
  let newest = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    const timestamp = Date.parse(item.startedAt ?? item.createdAt);
    if (!Number.isFinite(timestamp) || timestamp <= 0) {
      continue;
    }
    const date = new Date(timestamp);
    const day = new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    ).getTime();
    if (day < oldest) {
      oldest = day;
    }
    if (day > newest) {
      newest = day;
    }
  }
  if (!Number.isFinite(oldest) || newest < oldest) {
    return null;
  }
  const newestDay = new Date(newest);
  return {
    start: new Date(oldest).toISOString(),
    end: new Date(
      newestDay.getFullYear(),
      newestDay.getMonth(),
      newestDay.getDate() + 1,
    ).toISOString(),
  };
}

export function parseOmiCalendarCaptureGaps(
  body: string,
): OmiCalendarCaptureGap[] {
  const rows = array(JSON.parse(body), 1000);
  const items: OmiCalendarCaptureGap[] = [];
  const seen = new Set<string>();
  for (const raw of rows) {
    const row = object(raw);
    const eventId = visibleDisplayText(text(row.event_id, 256));
    if (eventId === '') {
      throw new CaptureGapError();
    }
    if (seen.has(eventId)) {
      throw new CaptureGapError();
    }
    seen.add(eventId);
    optionalText(row.status);
    optionalText(row.coverage);
    const title = visibleDisplayText(text(row.title, 10000));
    if (title === '') {
      continue;
    }
    items.push({
      eventId,
      title,
      startMs: timestampMs(row.start_time),
      endMs: timestampMs(row.end_time),
    });
  }
  return items;
}

export async function loadOmiCalendarCaptureGaps(
  backend: OmiBackend,
  span: {start: string; end: string},
): Promise<OmiCalendarCaptureGap[]> {
  const response = await backend.request({
    id: 'omi-calendar-capture-gaps',
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/calendar/capture-gaps?start=${encodeURIComponent(
      span.start,
    )}&end=${encodeURIComponent(span.end)}`,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiCalendarCaptureGaps(response.body);
  } catch {
    return [];
  }
}
