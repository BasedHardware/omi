import {dailySummaryDefaultHeadlineCopy} from './desktopReadClient';
import {
  loadOmiDailySummaries,
  parseOmiDailySummaries,
} from './legacyOmiDailySummaries';
import type {OmiBackend} from './omiNativeTypes';

test('names Flutter DailySummaryCard empty GET headlines instead of omitting them', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
        },
        {
          id: 'sum-empty',
          date: '2026-09-08',
          headline: ' \t',
        },
        {
          id: 'sum-blank',
          date: '2026-09-07',
          headline: '',
        },
      ],
    }),
  );
  expect(rows).toEqual([
    {
      id: 'sum-1',
      date: '2026-09-09',
      headline: 'Met with the team',
    },
    {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
    {id: 'sum-blank', date: '2026-09-07', headline: ''},
  ]);
});

test('names Flutter DailySummaryCard empty GET dates instead of omitting the date chip', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {id: 'sum-empty-date', date: '', headline: 'Empty date'},
        {id: 'sum-whitespace-date', date: ' \t', headline: 'Whitespace date'},
        {id: 'sum-next-line-date', date: '\u0085', headline: 'Next line date'},
      ],
    }),
  );
  expect(rows).toEqual([
    {id: 'sum-empty-date', date: '', headline: 'Empty date'},
    {id: 'sum-whitespace-date', date: ' \t', headline: 'Whitespace date'},
    {id: 'sum-next-line-date', date: '\u0085', headline: 'Next line date'},
  ]);
});

test('names Flutter DailySummaryCard padded GET dates instead of colliding with trim', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {id: 'sum-padded-date', date: '  padded  ', headline: 'Padded date'},
        {id: 'sum-omitted-date', headline: 'Omitted date'},
        {id: 'sum-null-date', date: null, headline: 'Null date'},
      ],
    }),
  );
  expect(rows).toEqual([
    {id: 'sum-padded-date', date: '  padded  ', headline: 'Padded date'},
    {id: 'sum-omitted-date', date: '', headline: 'Omitted date'},
    {id: 'sum-null-date', date: '', headline: 'Null date'},
  ]);
});

test('names Flutter DailySummary.fromGenerated empty GET ids instead of omitting the summary', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {id: '', date: '2026-09-09', headline: 'Empty id'},
        {id: ' \t', date: '2026-09-08', headline: 'Whitespace id'},
        {id: '\u0085', date: '2026-09-07', headline: 'Next line id'},
      ],
    }),
  );
  expect(rows).toEqual([
    {id: '', date: '2026-09-09', headline: 'Empty id'},
    {id: ' \t', date: '2026-09-08', headline: 'Whitespace id'},
    {id: '\u0085', date: '2026-09-07', headline: 'Next line id'},
  ]);
});

test('names Flutter DailySummary.fromGenerated padded GET ids instead of colliding with trim', () => {
  const rows = parseOmiDailySummaries(
    JSON.stringify({
      summaries: [
        {id: '  padded  ', date: '2026-09-09', headline: 'Padded id'},
        {id: 'padded', date: '2026-09-08', headline: 'Trimmed id'},
        {headline: 'Omitted id', date: '2026-09-07'},
      ],
    }),
  );
  expect(rows).toEqual([
    {id: '  padded  ', date: '2026-09-09', headline: 'Padded id'},
    {id: 'padded', date: '2026-09-08', headline: 'Trimmed id'},
    {id: '', date: '2026-09-07', headline: 'Omitted id'},
  ]);
});

test('parses GET daily summary headlines and omits unused stats', () => {
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
    {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
    {id: 'sum-2', date: '', headline: 'Shipped the recap'},
  ]);
});

test('old daily summaries name Flutter DailySummary.fromGenerated padded GET total_conversations instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {total_conversations: '3'},
          },
          {
            id: 'sum-json',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {total_conversations: 3},
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {
      id: 'sum-1',
      date: '2026-09-09',
      headline: 'Met with the team',
      conversations: 3,
    },
    {
      id: 'sum-json',
      date: '2026-09-09',
      headline: 'Met with the team',
      conversations: 3,
    },
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: null,
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const total_conversations of ['  3  ', '3 ', '  3', '3\n', '\u00853']) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              stats: {total_conversations},
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {action_items_count: '  2  '},
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            created_at: '  2026-09-07T00:00:00.000Z  ',
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            locations: [{latitude: '  37.7749  ', longitude: -122.4194}],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET created_at instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            created_at: '2026-09-07T00:00:00.000Z',
            locations: [{latitude: '37.7749', longitude: -122.4194}],
            memories_learned: [
              {
                captured_at: '2026-09-07T00:00:00.000Z',
                category: '',
                content: 'Learned',
                memory_id: 'mem-1',
              },
            ],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            created_at: null,
            locations: [{latitude: null, longitude: null}],
            memories_learned: [
              {
                captured_at: null,
                category: '',
                content: 'Learned',
                memory_id: 'mem-1',
              },
            ],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const created_at of ['', 'not-a-date', 1, true, [], {}]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              created_at,
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            locations: [{latitude: '', longitude: -122.4194}],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            locations: [{latitude: true, longitude: -122.4194}],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            memories_learned: [
              {
                captured_at: '',
                category: '',
                content: 'Learned',
                memory_id: 'mem-1',
              },
            ],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            memories_learned: [
              {
                captured_at: 1,
                category: '',
                content: 'Learned',
                memory_id: 'mem-1',
              },
            ],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
});

test('old daily summaries name Flutter DailySummary.fromGenerated padded GET memories_created instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: '1'},
          },
          {
            id: 'sum-json',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: 1},
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    {id: 'sum-json', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: null},
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const memories_created of ['  1  ', '1 ', '  1', '1\n', '\u00851']) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              stats: {memories_created},
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {action_items_created: '  2  '},
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            memories_learned: [
              {
                captured_at: '  2026-09-07T00:00:00.000Z  ',
                category: '',
                content: 'Kept',
                memory_id: 'mem-1',
              },
            ],
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET memories_created instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: '1'},
          },
          {
            id: 'sum-json',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: 1},
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    {id: 'sum-json', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {memories_created: null},
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const memories_created of [true, false, [], {}, '', 'abc', '1.5', 1.5]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              stats: {memories_created},
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {action_items_created: true},
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {total_conversations: true},
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            stats: {total_conversations: '3', total_duration_minutes: 1.5},
          },
          neighbor,
        ],
      }),
    ),
  ).toThrow('Omi daily summaries are malformed');
});

test('names Flutter DailySummaryCard omitted or JSON-null GET headlines as Your Day in Review', () => {
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-omitted', date: '2026-09-10'},
          {id: 'sum-null', date: '2026-09-09', headline: null},
          {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
        ],
      }),
    ),
  ).toEqual([
    {
      id: 'sum-omitted',
      date: '2026-09-10',
      headline: dailySummaryDefaultHeadlineCopy(),
    },
    {
      id: 'sum-null',
      date: '2026-09-09',
      headline: dailySummaryDefaultHeadlineCopy(),
    },
    {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
  ]);
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET headline instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-omitted', date: '2026-09-10'},
          {
            id: 'sum-null',
            date: null,
            headline: null,
            overview: null,
            day_emoji: null,
          },
        ],
      }),
    ),
  ).toEqual([
    {
      id: 'sum-omitted',
      date: '2026-09-10',
      headline: dailySummaryDefaultHeadlineCopy(),
    },
    {
      id: 'sum-null',
      date: '',
      headline: dailySummaryDefaultHeadlineCopy(),
    },
  ]);
  for (const headline of [1, true, [], {}]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {id: 'sum-headline-number', date: '2026-09-07', headline},
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {id: extra, date: '2026-09-09', headline: 'Met with the team'},
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: extra,
              headline: 'Met with the team',
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              overview: extra,
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              day_emoji: extra,
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              action_items: [{description: extra}],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET action_items item instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            action_items: [{description: 'Call Sam'}],
            highlights: [{topic: 'Team'}],
            locations: [{address: 'Market street'}],
            memories_learned: [{content: 'Notes'}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            action_items: 1,
            highlights: null,
            locations: [{}],
            memories_learned: [{}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              action_items: [extra],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              highlights: [extra],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              locations: [extra],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              memories_learned: [extra],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET conversation_ids item instead of remapping to a headline chip', () => {
  const neighbor = {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'};
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            highlights: [{topic: 'Team', conversation_ids: ['conv-1']}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            highlights: [{topic: 'Team'}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            highlights: [{topic: 'Team', conversation_ids: null}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            highlights: [{topic: 'Team', conversation_ids: 1}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-1',
            date: '2026-09-09',
            headline: 'Met with the team',
            highlights: [{topic: 'Team', conversation_ids: []}],
          },
          neighbor,
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-1', date: '2026-09-09', headline: 'Met with the team'},
    neighbor,
  ]);
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiDailySummaries(
        JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              highlights: [{topic: 'Team', conversation_ids: [extra]}],
            },
            neighbor,
          ],
        }),
      ),
    ).toThrow('Omi daily summaries are malformed');
  }
});

test('does not omit a neighboring daily summary when stored stats cannot project', () => {
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 'sum-kept', headline: 'Met with the team'},
          {
            id: 'sum-optional',
            headline: 'Shipped the recap',
            stats: {total_conversations: '3'},
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

test('keeps GET daily summaries when date or day_emoji exceeds 10000', () => {
  const date = 'D'.repeat(10001);
  const dayEmoji = 'E'.repeat(10001);
  expect(
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {
            id: 'sum-long',
            headline: 'Shipped the recap',
            date,
            day_emoji: dayEmoji,
          },
          {id: 'sum-kept', headline: 'Met with the team'},
        ],
      }),
    ),
  ).toEqual([
    {id: 'sum-long', date, headline: 'Shipped the recap', dayEmoji},
    {id: 'sum-kept', date: '', headline: 'Met with the team'},
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

test('keeps GET daily summaries when a summary id exceeds 10000', () => {
  const id = 's'.repeat(10001);
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

test('fails closed when a summary id exceeds 1000000', () => {
  expect(() =>
    parseOmiDailySummaries(
      JSON.stringify({
        summaries: [
          {id: 's'.repeat(1_000_001), headline: 'Met with the team'},
          {id: 'sum-kept', headline: 'Shipped the recap'},
        ],
      }),
    ),
  ).toThrow();
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

test('keeps GET daily summaries when the summaries array exceeds 10', () => {
  const summaries = Array.from({length: 11}, (_, index) => ({
    id: `sum-${index}`,
    headline: `Headline ${index}`,
  }));
  expect(parseOmiDailySummaries(JSON.stringify({summaries}))).toEqual([
    {id: 'sum-0', date: '', headline: 'Headline 0'},
    {id: 'sum-1', date: '', headline: 'Headline 1'},
    {id: 'sum-2', date: '', headline: 'Headline 2'},
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

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET created_at instead of omitting Daily Recaps', async () => {
  const request = jest.fn(async () => ({
    id: 'summaries',
    status: 200,
    body: JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
          created_at: 1,
        },
      ],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET action_items item instead of omitting Daily Recaps', async () => {
  const request = jest.fn(async () => ({
    id: 'summaries',
    status: 200,
    body: JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
          action_items: [1],
        },
        {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'},
      ],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET conversation_ids item instead of omitting Daily Recaps', async () => {
  const request = jest.fn(async () => ({
    id: 'summaries',
    status: 200,
    body: JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
          highlights: [{topic: 'Team', conversation_ids: [1]}],
        },
        {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'},
      ],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
});

test('old daily summaries name Flutter DailySummary.fromGenerated type-wrong GET memories_created instead of omitting Daily Recaps', async () => {
  const request = jest.fn(async () => ({
    id: 'summaries',
    status: 200,
    body: JSON.stringify({
      summaries: [
        {
          id: 'sum-1',
          date: '2026-09-09',
          headline: 'Met with the team',
          stats: {memories_created: true},
        },
        {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'},
      ],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiDailySummaries(backend)).toEqual([]);
});
