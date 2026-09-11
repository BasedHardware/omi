import {loadOmiUsagePeriod, parseOmiUsagePeriod} from './legacyOmiUsage';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET usage period buckets and omits missing periods', () => {
  expect(
    parseOmiUsagePeriod(
      JSON.stringify({
        monthly: {
          transcription_seconds: 120,
          words_transcribed: 20,
          insights_gained: 4,
          memories_created: 2,
          speech_seconds: 99,
        },
        today: {
          transcription_seconds: 90,
          words_transcribed: 12,
          insights_gained: 3,
          memories_created: 1,
        },
      }),
      'monthly',
    ),
  ).toEqual({
    transcriptionSeconds: 120,
    wordsTranscribed: 20,
    insightsGained: 4,
    memoriesCreated: 2,
  });
  expect(
    parseOmiUsagePeriod(
      JSON.stringify({
        today: {
          transcription_seconds: 90,
          words_transcribed: 12,
          insights_gained: 3,
          memories_created: 1,
        },
      }),
      'monthly',
    ),
  ).toBeNull();
  expect(
    parseOmiUsagePeriod(
      JSON.stringify({
        all_time: {
          transcription_seconds: 0,
          words_transcribed: 0,
          insights_gained: 0,
          memories_created: 0,
        },
      }),
      'all_time',
    ),
  ).toEqual({
    transcriptionSeconds: 0,
    wordsTranscribed: 0,
    insightsGained: 0,
    memoriesCreated: 0,
  });
});

test('does not omit a usage period when stored counts are integer strings', () => {
  expect(
    parseOmiUsagePeriod(
      JSON.stringify({
        yearly: {
          transcription_seconds: '12',
          words_transcribed: '20',
          insights_gained: '4',
          memories_created: '2',
        },
      }),
      'yearly',
    ),
  ).toEqual({
    transcriptionSeconds: 12,
    wordsTranscribed: 20,
    insightsGained: 4,
    memoriesCreated: 2,
  });
});

test('fails closed for malformed GET usage periods', () => {
  expect(() => parseOmiUsagePeriod(JSON.stringify([]), 'yearly')).toThrow();
  expect(() =>
    parseOmiUsagePeriod(
      JSON.stringify({yearly: {transcription_seconds: '12.5'}}),
      'yearly',
    ),
  ).toThrow();
  expect(() => parseOmiUsagePeriod('{', 'monthly')).toThrow();
});

test('loadOmiUsagePeriod names resolved GET periods and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'usage',
    status: 200,
    body: JSON.stringify({
      monthly: {
        transcription_seconds: 120,
        words_transcribed: 20,
        insights_gained: 4,
        memories_created: 2,
      },
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiUsagePeriod(backend, 'monthly')).toEqual({
    transcriptionSeconds: 120,
    wordsTranscribed: 20,
    insightsGained: 4,
    memoriesCreated: 2,
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/me/usage?period=monthly',
  });
  expect(
    request.mock.calls.some(call => `${call[0].path}`.includes('period=today')),
  ).toBe(false);
  request.mockResolvedValueOnce({id: 'usage', status: 404, body: null});
  expect(await loadOmiUsagePeriod(backend, 'yearly')).toBeNull();
  request.mockResolvedValueOnce({id: 'usage', status: 200, body: '{'});
  expect(await loadOmiUsagePeriod(backend, 'all_time')).toBeNull();
});
