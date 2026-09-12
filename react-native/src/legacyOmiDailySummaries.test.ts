import {
  loadOmiDailySummaries,
  parseOmiDailySummaries,
} from './legacyOmiDailySummaries';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET daily summary headlines and omits empty headlines', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
          day_emoji: '🎯',
          overview: 'Shipped the recap body.',
          stats: {
            total_conversations: 3,
            action_items_count: 2,
            total_duration_minutes: 90,
            watching_minutes: 10,
            proactive_moments: 1,
          },
        },
        {
          id: 'sum-empty',
          date: '2026-09-08',
          headline: ' \t',
        },
        {
          id: 'sum-2',
          headline: 'Shipped the recap',
          day_emoji: ' \t',
          overview: ' \t',
          stats: {
            total_conversations: 0,
            action_items_count: 0,
            total_duration_minutes: 0,
            watching_minutes: 0,
            proactive_moments: 0,
          },
        },
      ],
    }),
  );
  expect(rows).toEqual([
    {
      id: 'sum-1',
      date: '2026-09-09',
      headline: 'Met with the team',
      overview: 'Shipped the recap body.',
      dayEmoji: '🎯',
      conversations: 3,
      actionItems: 2,
      durationMinutes: 90,
      watchingMinutes: 10,
      proactiveMoments: 1,
    },
    {id: 'sum-2', date: '', headline: 'Shipped the recap'},
  ]);
});

test('does not omit a neighboring daily summary when stored headline or stats cannot project', () => {
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-kept', headline: 'Met with the team'},
          {id: 'sum-headline-number', headline: 1},
          {id: 'sum-headline-missing'},
          {id: '', headline: 'Empty id'},
          {id: 7, headline: 'Numeric id'},
          {
            id: 'sum-optional',
            headline: 'Shipped the recap',
            overview: 1,
            date: 1,
            day_emoji: 1,
            stats: {total_conversations: '3', total_duration_minutes: 1.5},
          },
          {
            id: 'sum-stats-object',
            headline: 'Walked',
            stats: 'nope',
          },
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-kept', date: '', headline: 'Met with the team'},
    {
      id: 'sum-optional',
      date: '',
      headline: 'Shipped the recap',
      conversations: 3,
    },
    {id: 'sum-stats-object', date: '', headline: 'Walked'},
  ]);
});

test('keeps GET daily summaries when date or day_emoji is longer than 32', () => {
  const date = 'x'.repeat(33);
  const dayEmoji = 'x'.repeat(33);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-kept', headline: 'Met with the team'},
          {
            id: 'sum-long',
            headline: 'Shipped the recap',
            date,
            day_emoji: dayEmoji,
          },
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-kept', date: '', headline: 'Met with the team'},
    {id: 'sum-long', date, headline: 'Shipped the recap', dayEmoji},
  ]);
});

test('keeps GET daily summaries when a summary id exceeds 256', () => {
  const id = 's'.repeat(257);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id, headline: 'Met with the team'},
          {id: 'sum-kept', headline: 'Shipped the recap'},
        ],
      }),
    ),
  ).toEqual([
    {id, date: '', headline: 'Met with the team'},
    {id: 'sum-kept', date: '', headline: 'Shipped the recap'},
  ]);
});

test('keeps GET daily summaries when headline or overview exceeds 10000', () => {
  const headline = 'H'.repeat(10001);
  const overview = 'O'.repeat(10001);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-long', headline, overview},
          {id: 'sum-kept', headline: 'Shipped the recap'},
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-long', date: '', headline, overview},
    {id: 'sum-kept', date: '', headline: 'Shipped the recap'},
  ]);
});

test('fails closed for malformed GET daily summaries', () => {
  expect(() => parseOmiDailySummaries(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-1', headline: 'One'},
          {id: 'sum-1', headline: 'Dup'},
        ],
      }),
    ),
  ).toThrow();
});

test('loadOmiDailySummaries names resolved GET summaries and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'summaries',
    status: 200,
    body: JSON.stringify({
      summaries: [
        {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
      ],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummaries(backend)).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summaries?limit=3&offset=0',
  });
  request.mockResolvedValueOnce({id: 'summaries', status: 404, body: '{}'});
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
  request.mockResolvedValueOnce({id: 'summaries', status: 200, body: '['});
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
});
