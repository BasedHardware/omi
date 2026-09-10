import type {OmiBackend} from './omiNativeTypes';

class DailySummaryScheduleError extends Error {
  constructor() {
    super('Omi daily summary settings are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new DailySummaryScheduleError();
  }
  return value as Record<string, unknown>;
}

function requiredBoolean(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new DailySummaryScheduleError();
  }
  return value;
}

function requiredHour(value: unknown): number {
  if (
    typeof value !== 'number' ||
    !Number.isSafeInteger(value) ||
    value < 0 ||
    value > 23
  ) {
    throw new DailySummaryScheduleError();
  }
  return value;
}

export type OmiDailySummarySchedule = {
  enabled: boolean;
  hour: number;
};

export function parseOmiDailySummarySchedule(
  body: string,
): OmiDailySummarySchedule {
  const record = object(JSON.parse(body));
  return {
    enabled: requiredBoolean(record.enabled),
    hour: requiredHour(record.hour),
  };
}

export async function loadOmiDailySummarySchedule(
  backend: OmiBackend,
): Promise<OmiDailySummarySchedule | null> {
  const response = await backend.request({
    id: 'omi-daily-summary-settings',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summary-settings',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiDailySummarySchedule(response.body);
  } catch {
    return null;
  }
}
