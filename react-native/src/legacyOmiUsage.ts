import {visibleDisplayText} from './desktopReadClient';
import type {OmiBackend} from './omiNativeTypes';

export type OmiUsagePeriod = 'today' | 'monthly' | 'yearly' | 'all_time';

export type OmiUsageStats = {
  transcriptionSeconds: number;
  wordsTranscribed: number;
  insightsGained: number;
  memoriesCreated: number;
};

class UsageError extends Error {
  constructor() {
    super('Omi usage is malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new UsageError();
  }
  return value as Record<string, unknown>;
}

function requiredUsageInteger(value: unknown): number {
  if (value === undefined) {
    return 0;
  }
  if (typeof value === 'string') {
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new UsageError();
    }
    return Number(value);
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return value;
  }
  throw new UsageError();
}

const USAGE_PERIODS = ['today', 'monthly', 'yearly', 'all_time'] as const;

function usageStats(value: unknown): OmiUsageStats {
  const stats = object(value);
  requiredUsageInteger(stats.speech_seconds);
  return {
    transcriptionSeconds: requiredUsageInteger(stats.transcription_seconds),
    wordsTranscribed: requiredUsageInteger(stats.words_transcribed),
    insightsGained: requiredUsageInteger(stats.insights_gained),
    memoriesCreated: requiredUsageInteger(stats.memories_created),
  };
}

function optionalUsageStats(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  usageStats(value);
}

function optionalUsageHistory(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    throw new UsageError();
  }
  for (const raw of value) {
    const point = object(raw);
    if (typeof point.date !== 'string') {
      throw new UsageError();
    }
    if (visibleDisplayText(point.date) !== point.date) {
      throw new UsageError();
    }
    const parsed = Date.parse(point.date);
    if (point.date === '' || !Number.isFinite(parsed)) {
      throw new UsageError();
    }
    requiredUsageInteger(point.transcription_seconds);
    requiredUsageInteger(point.words_transcribed);
    requiredUsageInteger(point.insights_gained);
    requiredUsageInteger(point.memories_created);
    requiredUsageInteger(point.speech_seconds);
  }
}

export function parseOmiUsagePeriod(
  body: string,
  period: OmiUsagePeriod,
): OmiUsageStats | null {
  const record = object(JSON.parse(body));
  for (const key of USAGE_PERIODS) {
    optionalUsageStats(record[key]);
  }
  optionalUsageHistory(record.history);
  const raw = record[period];
  if (raw === undefined || raw === null) {
    return null;
  }
  return usageStats(raw);
}

export async function loadOmiUsagePeriod(
  backend: OmiBackend,
  period: OmiUsagePeriod,
): Promise<OmiUsageStats | null> {
  const response = await backend.request({
    id: `omi-usage-${period}`,
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/users/me/usage?period=${period}`,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    throw new UsageError();
  }
  return parseOmiUsagePeriod(response.body, period);
}
