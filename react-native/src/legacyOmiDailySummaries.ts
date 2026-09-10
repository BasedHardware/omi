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
  dayEmoji?: string;
  conversations?: number;
  actionItems?: number;
  durationMinutes?: number;
  watchingMinutes?: number;
  proactiveMoments?: number;
};

function optionalCount(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new DailySummaryError();
  }
  return value === 0 ? undefined : value;
}

function summaryStats(value: unknown): {
  conversations?: number;
  actionItems?: number;
  durationMinutes?: number;
  watchingMinutes?: number;
  proactiveMoments?: number;
} {
  if (value === undefined || value === null) {
    return {};
  }
  const stats = object(value);
  const conversations = optionalCount(stats.total_conversations);
  const actionItems = optionalCount(stats.action_items_count);
  const durationMinutes = optionalCount(stats.total_duration_minutes);
  const watchingMinutes = optionalCount(stats.watching_minutes);
  const proactiveMoments = optionalCount(stats.proactive_moments);
  return {
    ...(conversations === undefined ? {} : {conversations}),
    ...(actionItems === undefined ? {} : {actionItems}),
    ...(durationMinutes === undefined ? {} : {durationMinutes}),
    ...(watchingMinutes === undefined ? {} : {watchingMinutes}),
    ...(proactiveMoments === undefined ? {} : {proactiveMoments}),
  };
}

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
    const dayEmoji =
      summary.day_emoji === undefined || summary.day_emoji === null
        ? ''
        : visibleDisplayText(text(summary.day_emoji, 32));
    const stats = summaryStats(summary.stats);
    items.push({
      id,
      date,
      headline,
      ...(dayEmoji === '' ? {} : {dayEmoji}),
      ...stats,
    });
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
