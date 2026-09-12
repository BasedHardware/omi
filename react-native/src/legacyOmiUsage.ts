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

export function parseOmiUsagePeriod(
  body: string,
  period: OmiUsagePeriod,
): OmiUsageStats | null {
  const record = object(JSON.parse(body));
  const raw = record[period];
  if (raw === undefined || raw === null) {
    return null;
  }
  const stats = object(raw);
  return {
    transcriptionSeconds: requiredUsageInteger(stats.transcription_seconds),
    wordsTranscribed: requiredUsageInteger(stats.words_transcribed),
    insightsGained: requiredUsageInteger(stats.insights_gained),
    memoriesCreated: requiredUsageInteger(stats.memories_created),
  };
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
    return null;
  }
  try {
    return parseOmiUsagePeriod(response.body, period);
  } catch {
    return null;
  }
}
