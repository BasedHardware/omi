import {
  loadOmiDailySummarySchedule,
  parseOmiDailySummarySchedule,
} from './legacyOmiDailySummarySchedule';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET daily summary settings without Flutter true/22 defaults', () => {
  expect(
    parseOmiDailySummarySchedule(JSON.stringify({enabled: false, hour: 0})),
  ).toEqual({enabled: false, hour: 0});
  expect(
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true, hour: 22})),
  ).toEqual({enabled: true, hour: 22});
});

test('does not omit daily summary settings when stored hour is an integer string', () => {
  expect(
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true, hour: '22'})),
  ).toEqual({enabled: true, hour: 22});
});

test('fails closed for malformed GET daily summary settings', () => {
  expect(() => parseOmiDailySummarySchedule(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true})),
  ).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({hour: 22})),
  ).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true, hour: 24})),
  ).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true, hour: -1})),
  ).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({enabled: true, hour: 22.5})),
  ).toThrow();
  expect(() =>
    parseOmiDailySummarySchedule(JSON.stringify({enabled: 'true', hour: 22})),
  ).toThrow();
});

test('loadOmiDailySummarySchedule names resolved GET settings and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'schedule',
    status: 200,
    body: JSON.stringify({enabled: true, hour: 22}),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummarySchedule(backend)).toEqual({
    enabled: true,
    hour: 22,
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summary-settings',
  });
  request.mockResolvedValueOnce({id: 'schedule', status: 404, body: '{}'});
  expect(await loadOmiDailySummarySchedule(backend)).toBeNull();
  request.mockResolvedValueOnce({id: 'schedule', status: 200, body: '['});
  expect(await loadOmiDailySummarySchedule(backend)).toBeNull();
});
