import {
  goalProgressCopy,
  goalTasksProgressCopy,
  goalTasksTitleCopy,
  loadOmiGoals,
  parseOmiGoals,
} from './legacyOmiGoals';
import type {OmiBackend} from './omiNativeTypes';

test('formats GET goal progress like Flutter raw current/target', () => {
  expect(goalProgressCopy(3, 10)).toBe('3/10');
  expect(goalProgressCopy(3.5, 10)).toBe('3.5/10');
  expect(goalProgressCopy(0, 0)).toBe('0/0');
});

test('formats Tasks GET goal progress like Flutter _buildGoalItem toInt', () => {
  expect(goalTasksProgressCopy(3, 10)).toBe('(3/10)');
  expect(goalTasksProgressCopy(3.5, 10)).toBe('(3/10)');
  expect(goalTasksProgressCopy(0, 0)).toBe('(0/0)');
  expect(goalTasksTitleCopy('Read 20 books', 3, 10)).toBe(
    'Read 20 books (3/10)',
  );
  expect(goalTasksTitleCopy('Missing metrics', 0, 10)).toBe(
    'Missing metrics (0/10)',
  );
  expect(goalTasksTitleCopy(' \t', 1, 2)).toBe(' \t (1/2)');
  expect(goalTasksTitleCopy('\u0085', 1, 2)).toBe('\u0085 (1/2)');
  expect(goalTasksTitleCopy('', 3, 10)).toBe(' (3/10)');
});

test('names Flutter GoalsWidget empty GET titles instead of omitting them', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {id: 'goal-empty', title: ' \t', current_value: 1, target_value: 2},
      {id: 'goal-next', title: '\u0085', current_value: 2, target_value: 3},
      {id: 'goal-blank', title: '', current_value: 3, target_value: 10},
      {id: 'goal-null', title: null, current_value: 3, target_value: 10},
      {id: 'goal-omitted', current_value: 0, target_value: 1},
      {
        id: 'goal-run',
        title: 'Run weekly',
        current_value: 1.5,
        target_value: 4,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-empty', title: ' \t', current: 1, target: 2},
    {id: 'goal-next', title: '\u0085', current: 2, target: 3},
    {id: 'goal-blank', title: '', current: 3, target: 10},
    {id: 'goal-null', title: '', current: 3, target: 10},
    {id: 'goal-omitted', title: '', current: 0, target: 1},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('does not omit a neighboring titled goal when GET lists more than four', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {id: 'g1', title: 'One', current_value: 1, target_value: 1},
      {id: 'g-empty', title: '  ', current_value: 0, target_value: 1},
      {id: 'g2', title: 'Two', current_value: 2, target_value: 2},
      {id: 'g3', title: 'Three', current_value: 3, target_value: 3},
      {id: 'g4', title: 'Four', current_value: 4, target_value: 4},
      {id: 'g5', title: 'Five', current_value: 5, target_value: 5},
    ]),
  );
  expect(rows.map(row => row.id)).toEqual([
    'g1',
    'g-empty',
    'g2',
    'g3',
    'g4',
    'g5',
  ]);
});

test('names Flutter Goal.fromJson defaulted GET metrics instead of omitting the titled row', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {
        id: 'goal-string',
        title: 'Walk daily',
        current_value: '1.5',
        target_value: '4',
      },
      {id: 'goal-missing', title: 'Missing metrics', target_value: 10},
      {
        id: 'goal-null',
        title: 'Null metrics',
        current_value: null,
        target_value: null,
      },
      {
        id: 'goal-object',
        title: 'Object metrics',
        current_value: {value: 1},
        target_value: 2,
      },
      {
        id: 'goal-invalid',
        title: 'Invalid metrics',
        current_value: 'nope',
        target_value: 2,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-string', title: 'Walk daily', current: 1.5, target: 4},
    {id: 'goal-missing', title: 'Missing metrics', current: 0, target: 10},
    {id: 'goal-null', title: 'Null metrics', current: 0, target: 0},
  ]);
});

test('names Flutter Goal.fromJson padded GET current_value instead of remapping to a progress chip', () => {
  expect(
    parseOmiGoals(
      JSON.stringify([
        {
          id: 'goal-exact-string',
          title: 'Exact string metrics',
          current_value: '3',
          target_value: '10',
        },
        {
          id: 'goal-number',
          title: 'Number metrics',
          current_value: 3,
          target_value: 10,
        },
      ]),
    ),
  ).toEqual([
    {
      id: 'goal-exact-string',
      title: 'Exact string metrics',
      current: 3,
      target: 10,
    },
    {id: 'goal-number', title: 'Number metrics', current: 3, target: 10},
  ]);
  for (const [id, current, target] of [
    ['goal-padded', '  3  ', 10],
    ['goal-trailing', '3 ', 10],
    ['goal-leading', '  3', 10],
    ['goal-newline', '3\n', 10],
    ['goal-decimal', '  1.5  ', 10],
    ['goal-next-line', '\u00853', 10],
    ['goal-padded-target', 3, '  10  '],
    ['goal-whitespace', ' \t', 10],
  ] as const) {
    const rows = parseOmiGoals(
      JSON.stringify([
        {
          id,
          title: 'Padded metrics',
          current_value: current,
          target_value: target,
        },
        {
          id: 'goal-read',
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
      ]),
    );
    expect(rows.find(row => row.id === id)).toBeUndefined();
    expect(rows.find(row => row.id === 'goal-read')).toEqual({
      id: 'goal-read',
      title: 'Read 20 books',
      current: 3,
      target: 10,
    });
  }
});

test('old goals name Flutter Goal.fromJson padded GET created_at instead of remapping to a progress chip', () => {
  const neighbor = {
    id: 'goal-read',
    title: 'Read 20 books',
    current: 3,
    target: 10,
  };
  expect(
    parseOmiGoals(
      JSON.stringify([
        {
          id: 'goal-exact',
          title: 'Exact clocks',
          current_value: 3,
          target_value: 10,
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          max_value: '10',
          min_value: '0',
          focus_rank: '1',
        },
        {
          id: 'goal-json',
          title: 'JSON clocks',
          current_value: 3,
          target_value: 10,
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          max_value: 10,
          min_value: 0,
          focus_rank: 1,
        },
        {
          id: 'goal-read',
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
      ]),
    ),
  ).toEqual([
    {id: 'goal-exact', title: 'Exact clocks', current: 3, target: 10},
    {id: 'goal-json', title: 'JSON clocks', current: 3, target: 10},
    neighbor,
  ]);
  expect(
    parseOmiGoals(
      JSON.stringify([
        {
          id: 'goal-omitted',
          title: 'Omitted clocks',
          current_value: 3,
          target_value: 10,
        },
        {
          id: 'goal-null',
          title: 'Null clocks',
          current_value: 3,
          target_value: 10,
          created_at: null,
          updated_at: null,
          max_value: null,
          min_value: null,
          focus_rank: null,
        },
        {
          id: 'goal-read',
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
      ]),
    ),
  ).toEqual([
    {id: 'goal-omitted', title: 'Omitted clocks', current: 3, target: 10},
    {id: 'goal-null', title: 'Null clocks', current: 3, target: 10},
    neighbor,
  ]);
  for (const created_at of [
    '  2026-09-07T00:00:00.000Z  ',
    '2026-09-07T00:00:00.000Z ',
    '  2026-09-07T00:00:00.000Z',
    '2026-09-07T00:00:00.000Z\n',
    '\u00852026-09-07T00:00:00.000Z',
  ]) {
    const rows = parseOmiGoals(
      JSON.stringify([
        {
          id: 'goal-padded',
          title: 'Padded clocks',
          current_value: 3,
          target_value: 10,
          created_at,
        },
        {
          id: 'goal-read',
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
      ]),
    );
    expect(rows.find(row => row.id === 'goal-padded')).toBeUndefined();
    expect(rows.find(row => row.id === 'goal-read')).toEqual(neighbor);
  }
  for (const [field, value] of [
    ['updated_at', '  2026-09-07T00:00:00.000Z  '],
    ['max_value', '  10  '],
    ['min_value', '  0  '],
    ['focus_rank', '  1  '],
    ['latest_progress_sequence', '  2  '],
    ['ended_at', '  2026-09-07T00:00:00.000Z  '],
    ['horizon_at', '  2026-09-07T00:00:00.000Z  '],
  ] as const) {
    const rows = parseOmiGoals(
      JSON.stringify([
        {
          id: 'goal-padded',
          title: 'Padded extras',
          current_value: 3,
          target_value: 10,
          [field]: value,
        },
        {
          id: 'goal-read',
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
      ]),
    );
    expect(rows.find(row => row.id === 'goal-padded')).toBeUndefined();
    expect(rows.find(row => row.id === 'goal-read')).toEqual(neighbor);
  }
  const metricRows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-padded',
        title: 'Padded metric',
        current_value: 3,
        target_value: 10,
        metric: {current: '  3  ', target: 10, type: 'scale'},
      },
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
    ]),
  );
  expect(metricRows.find(row => row.id === 'goal-padded')).toBeUndefined();
  expect(metricRows.find(row => row.id === 'goal-read')).toEqual(neighbor);
});

test('names Flutter Goal.fromJson empty GET ids instead of omitting the row', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {id: '', title: 'Empty id', current_value: 1, target_value: 1},
      {id: ' \t', title: 'Whitespace id', current_value: 2, target_value: 2},
      {id: '\u0085', title: 'Next line id', current_value: 2.5, target_value: 2.5},
      {id: '  padded  ', title: 'Padded id', current_value: 2.75, target_value: 2.75},
      {id: 'padded', title: 'Trimmed id', current_value: 2.8, target_value: 2.8},
      {id: null, title: 'Null id', current_value: 3, target_value: 3},
      {title: 'Omitted id', current_value: 4, target_value: 4},
      {
        id: 'goal-run',
        title: 'Run weekly',
        current_value: 1.5,
        target_value: 4,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: '', title: 'Empty id', current: 1, target: 1},
    {id: ' \t', title: 'Whitespace id', current: 2, target: 2},
    {id: '\u0085', title: 'Next line id', current: 2.5, target: 2.5},
    {id: '  padded  ', title: 'Padded id', current: 2.75, target: 2.75},
    {id: 'padded', title: 'Trimmed id', current: 2.8, target: 2.8},
    {id: '', title: 'Null id', current: 3, target: 3},
    {id: '', title: 'Omitted id', current: 4, target: 4},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('does not omit a neighboring titled goal when stored identity cannot project', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {
        id: 7,
        title: 'Walk daily',
        current_value: 1.5,
        target_value: 4,
      },
      {
        id: 'goal-title',
        title: 1,
        current_value: 1,
        target_value: 2,
      },
      {id: '', title: 'Empty id', current_value: 1, target_value: 1},
      {
        id: {text: 'Nope'},
        title: 'Object id',
        current_value: 1,
        target_value: 1,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: '7', title: 'Walk daily', current: 1.5, target: 4},
    {id: '', title: 'Empty id', current: 1, target: 1},
  ]);
});

test('does not omit a neighboring titled goal when a stored row is not an object', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      null,
      7,
      'nope',
      ['nested'],
      {
        id: 'goal-run',
        title: 'Run weekly',
        current_value: 1.5,
        target_value: 4,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('does not omit titled goals when GET lists more than thirty-two rows', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      ...Array.from({length: 32}, () => null),
      {
        id: 'goal-run',
        title: 'Run weekly',
        current_value: 1.5,
        target_value: 4,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('keeps GET goals when a goal id exceeds 256', () => {
  const id = 'g'.repeat(257);
  expect(
    parseOmiGoals(
      JSON.stringify([
        {id, title: 'Read 20 books', current_value: 3, target_value: 10},
        {
          id: 'goal-run',
          title: 'Run weekly',
          current_value: 1.5,
          target_value: 4,
        },
      ]),
    ),
  ).toEqual([
    {id, title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('keeps GET goals when a goal id exceeds 10000', () => {
  const id = 'g'.repeat(10001);
  expect(
    parseOmiGoals(
      JSON.stringify([
        {id, title: 'Read 20 books', current_value: 3, target_value: 10},
        {
          id: 'goal-run',
          title: 'Run weekly',
          current_value: 1.5,
          target_value: 4,
        },
      ]),
    ),
  ).toEqual([
    {id, title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('fails closed when a goal id exceeds 1000000', () => {
  expect(() =>
    parseOmiGoals(
      JSON.stringify([
        {
          id: 'g'.repeat(1_000_001),
          title: 'Read 20 books',
          current_value: 3,
          target_value: 10,
        },
        {
          id: 'goal-run',
          title: 'Run weekly',
          current_value: 1.5,
          target_value: 4,
        },
      ]),
    ),
  ).toThrow();
});

test('keeps GET goals when a title exceeds 10000', () => {
  const title = 'R'.repeat(10001);
  expect(
    parseOmiGoals(
      JSON.stringify([
        {id: 'goal-long', title, current_value: 3, target_value: 10},
        {
          id: 'goal-run',
          title: 'Run weekly',
          current_value: 1.5,
          target_value: 4,
        },
      ]),
    ),
  ).toEqual([
    {id: 'goal-long', title, current: 3, target: 10},
    {id: 'goal-run', title: 'Run weekly', current: 1.5, target: 4},
  ]);
});

test('fails closed for malformed GET goals', () => {
  expect(() => parseOmiGoals(JSON.stringify({id: 'goal-1'}))).toThrow();
  expect(() =>
    parseOmiGoals(
      JSON.stringify([
        {id: 'goal-1', title: 'Read', current_value: 3, target_value: 10},
        {id: 'goal-1', title: 'Dup', current_value: 1, target_value: 1},
      ]),
    ),
  ).toThrow();
});

test('loadOmiGoals names resolved GET goals and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'goals',
    status: 200,
    body: JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiGoals(backend)).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
  ]);
  request.mockResolvedValueOnce({
    id: 'goals',
    status: 200,
    body: JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {
        id: 'goal-string',
        title: 'Walk daily',
        current_value: '1.5',
        target_value: '4',
      },
      {id: 'goal-missing', title: 'Missing metrics', target_value: 10},
      {
        id: 'goal-null',
        title: 'Null metrics',
        current_value: null,
        target_value: 4,
      },
      {
        id: 7,
        title: 'Numeric id',
        current_value: 2,
        target_value: 5,
      },
      {
        id: 'goal-title',
        title: 1,
        current_value: 1,
        target_value: 2,
      },
      null,
    ]),
  });
  expect(await loadOmiGoals(backend)).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-string', title: 'Walk daily', current: 1.5, target: 4},
    {id: 'goal-missing', title: 'Missing metrics', current: 0, target: 10},
    {id: 'goal-null', title: 'Null metrics', current: 0, target: 4},
    {id: '7', title: 'Numeric id', current: 2, target: 5},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/goals/all',
  });
  expect(request.mock.calls.some(call => call[0].path === '/v1/goals')).toBe(
    false,
  );
  request.mockResolvedValueOnce({id: 'goals', status: 404, body: null});
  expect(await loadOmiGoals(backend)).toEqual([]);
  request.mockResolvedValueOnce({id: 'goals', status: 200, body: '{'});
  expect(await loadOmiGoals(backend)).toEqual([]);
});
