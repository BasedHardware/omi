import {loadOmiFairUseStatus, parseOmiFairUseStatus} from './legacyOmiFairUse';
import type {OmiBackend} from './omiNativeTypes';

const status = {
  stage: 'restrict',
  case_ref: 'FU-1',
  message: 'Usage is restricted.',
  speech_hours_today: 2.4,
  speech_hours_3day: 8.1,
  speech_hours_weekly: 11,
  limits: {
    daily_hours: 2,
    three_day_hours: 8,
    weekly_hours: 10,
  },
  usage_pct: {daily: 120, three_day: 101, weekly: 110},
  dg_budget: {
    daily_limit_ms: 1_800_000,
    used_ms: 1_800_000,
    remaining_ms: 0,
    exhausted: true,
    resets_at: '2026-09-11T00:00:00Z',
  },
};

test('parses GET fair use status without invented limits', () => {
  expect(parseOmiFairUseStatus(JSON.stringify(status))).toEqual({
    stage: 'restrict',
    caseRef: 'FU-1',
    message: 'Usage is restricted.',
    speechHoursToday: 2.4,
    speechHours3day: 8.1,
    speechHoursWeekly: 11,
    dailyHours: 2,
    threeDayHours: 8,
    weeklyHours: 10,
    dailyLimitMs: 1_800_000,
    usedMs: 1_800_000,
    exhausted: true,
    resetsAtMs: Date.parse('2026-09-11T00:00:00Z'),
  });
});

test('does not omit fair use status when stored counts are numeric strings', () => {
  expect(
    parseOmiFairUseStatus(
      JSON.stringify({
        ...status,
        speech_hours_today: '2.4',
        speech_hours_3day: '8.1',
        speech_hours_weekly: '11',
        limits: {
          daily_hours: '2',
          three_day_hours: '8',
          weekly_hours: '10',
        },
        usage_pct: {daily: '120', three_day: '101', weekly: '110'},
        dg_budget: {
          ...status.dg_budget,
          daily_limit_ms: '1800000',
          used_ms: '1800000',
          remaining_ms: '0',
        },
      }),
    ),
  ).toEqual({
    stage: 'restrict',
    caseRef: 'FU-1',
    message: 'Usage is restricted.',
    speechHoursToday: 2.4,
    speechHours3day: 8.1,
    speechHoursWeekly: 11,
    dailyHours: 2,
    threeDayHours: 8,
    weeklyHours: 10,
    dailyLimitMs: 1_800_000,
    usedMs: 1_800_000,
    exhausted: true,
    resetsAtMs: Date.parse('2026-09-11T00:00:00Z'),
  });
});

test('fails closed for malformed GET fair use status', () => {
  expect(() => parseOmiFairUseStatus(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiFairUseStatus(JSON.stringify({...status, stage: 1})),
  ).toThrow();
  expect(() =>
    parseOmiFairUseStatus(
      JSON.stringify({...status, limits: {daily_hours: 2}}),
    ),
  ).toThrow();
  expect(() =>
    parseOmiFairUseStatus(JSON.stringify({...status, dg_budget: null})),
  ).toThrow();
  expect(() =>
    parseOmiFairUseStatus(
      JSON.stringify({
        ...status,
        dg_budget: {...status.dg_budget, resets_at: 1},
      }),
    ),
  ).toThrow();
  expect(
    parseOmiFairUseStatus(
      JSON.stringify({
        ...status,
        dg_budget: {...status.dg_budget, resets_at: ''},
      }),
    ).resetsAtMs,
  ).toBeUndefined();
  expect(
    parseOmiFairUseStatus(
      JSON.stringify({
        ...status,
        dg_budget: {...status.dg_budget, resets_at: 'not-a-date'},
      }),
    ).resetsAtMs,
  ).toBeUndefined();
});

test('loadOmiFairUseStatus names resolved GET status and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'fair-use',
    status: 200,
    body: JSON.stringify(status),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiFairUseStatus(backend)).toEqual({
    stage: 'restrict',
    caseRef: 'FU-1',
    message: 'Usage is restricted.',
    speechHoursToday: 2.4,
    speechHours3day: 8.1,
    speechHoursWeekly: 11,
    dailyHours: 2,
    threeDayHours: 8,
    weeklyHours: 10,
    dailyLimitMs: 1_800_000,
    usedMs: 1_800_000,
    exhausted: true,
    resetsAtMs: Date.parse('2026-09-11T00:00:00Z'),
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/fair-use/status',
  });
  request.mockResolvedValueOnce({id: 'fair-use', status: 404, body: null});
  expect(await loadOmiFairUseStatus(backend)).toBeNull();
  request.mockResolvedValueOnce({id: 'fair-use', status: 200, body: '{'});
  expect(await loadOmiFairUseStatus(backend)).toBeNull();
});
