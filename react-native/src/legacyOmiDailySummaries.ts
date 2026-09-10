import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_DAILY_SUMMARIES = 3;

class DailySummaryError extends Error {
  constructor() {
    super('Omi daily summaries are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new DailySummaryError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new DailySummaryError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new DailySummaryError();
  }
  return value;
}

export type OmiDailySummary = {
  id: string;
  date: string;
  headline: string;
};

export function parseOmiDailySummaries(body: string): OmiDailySummary[] {
  const row = object(JSON.parse(body));
  const summaries =
    row.summaries === undefined || row.summaries === null
      ? []
      : array(row.summaries, 10);
  const items: OmiDailySummary[] = [];
  const seen = new Set<string>();
  for (const raw of summaries) {
    if (items.length === MAX_DAILY_SUMMARIES) {
      break;
    }
    const summary = object(raw);
    const id = visibleDisplayText(text(summary.id, 256));
    if (id === '') {
      throw new DailySummaryError();
    }
    if (seen.has(id)) {
      throw new DailySummaryError();
    }
    seen.add(id);
    const headline = visibleDisplayText(text(summary.headline, 10000));
    if (headline === '') {
      continue;
    }
    const date =
      summary.date === undefined || summary.date === null
        ? ''
        : visibleDisplayText(text(summary.date, 32));
    items.push({id, date, headline});
  }
  return items;
}

export async function loadOmiDailySummaries(
  backend: OmiBackend,
): Promise<OmiDailySummary[]> {
  const response = await backend.request({
    id: 'omi-daily-summaries',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summaries?limit=3&offset=0',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiDailySummaries(response.body);
  } catch {
    return [];
  }
}
