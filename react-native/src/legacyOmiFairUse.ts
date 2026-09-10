import type {OmiBackend} from './omiNativeTypes';

class FairUseError extends Error {
  constructor() {
    super('Omi fair use is malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new FairUseError();
  }
  return value as Record<string, unknown>;
}

function finiteNumber(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new FairUseError();
  }
  return value;
}

function requiredString(value: unknown): string {
  if (typeof value !== 'string') {
    throw new FairUseError();
  }
  return value;
}

function requiredBoolean(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new FairUseError();
  }
  return value;
}

function optionalResetAtMs(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const raw = requiredString(value).trim();
  if (raw === '') {
    return undefined;
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

function requiredInteger(value: unknown): number {
  const number = finiteNumber(value);
  if (!Number.isSafeInteger(number)) {
    throw new FairUseError();
  }
  return number;
}

export type OmiFairUseStatus = {
  stage: string;
  caseRef: string;
  message: string;
  speechHoursToday: number;
  speechHours3day: number;
  speechHoursWeekly: number;
  dailyHours: number;
  threeDayHours: number;
  weeklyHours: number;
  dailyLimitMs: number;
  usedMs: number;
  exhausted: boolean;
  resetsAtMs?: number;
};

export function parseOmiFairUseStatus(body: string): OmiFairUseStatus {
  const record = object(JSON.parse(body));
  const limits = object(record.limits);
  const budget = object(record.dg_budget);
  const usagePct = object(record.usage_pct);
  requiredInteger(budget.remaining_ms);
  finiteNumber(usagePct.daily);
  finiteNumber(usagePct.three_day);
  finiteNumber(usagePct.weekly);
  const reset = optionalResetAtMs(budget.resets_at);
  return {
    stage: requiredString(record.stage),
    caseRef: requiredString(record.case_ref),
    message: requiredString(record.message),
    speechHoursToday: finiteNumber(record.speech_hours_today),
    speechHours3day: finiteNumber(record.speech_hours_3day),
    speechHoursWeekly: finiteNumber(record.speech_hours_weekly),
    dailyHours: finiteNumber(limits.daily_hours),
    threeDayHours: finiteNumber(limits.three_day_hours),
    weeklyHours: finiteNumber(limits.weekly_hours),
    dailyLimitMs: requiredInteger(budget.daily_limit_ms),
    usedMs: requiredInteger(budget.used_ms),
    exhausted: requiredBoolean(budget.exhausted),
    ...(reset === undefined ? {} : {resetsAtMs: reset}),
  };
}

export async function loadOmiFairUseStatus(
  backend: OmiBackend,
  signal?: AbortSignal,
): Promise<OmiFairUseStatus | null> {
  if (signal?.aborted) {
    return null;
  }
  const response = await backend.request({
    id: 'omi-fair-use',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/fair-use/status',
  });
  if (signal?.aborted) {
    return null;
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiFairUseStatus(response.body);
  } catch {
    return null;
  }
}
