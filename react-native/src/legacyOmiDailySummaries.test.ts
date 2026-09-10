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
          stats: {total_conversations: 3, action_items_count: 2},
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
          stats: {total_conversations: 0, action_items_count: 0},
        },
      ],
    }),
  );
  expect(rows).toEqual([
    {
      id: 'sum-1',
      date: '2026-09-09',
      headline: 'Met with the team',
      dayEmoji: '🎯',
      conversations: 3,
      actionItems: 2,
    },
    {id: 'sum-2', date: '', headline: 'Shipped the recap'},
  ]);
});

test('fails closed for malformed GET daily summaries', () => {
  expect(() => parseOmiDailySummaries(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({summaries: [{id: 'sum-1', headline: 1}]}),
    ),
  ).toThrow();
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            headline: 'One',
            stats: {total_conversations: '3'},
          },
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
