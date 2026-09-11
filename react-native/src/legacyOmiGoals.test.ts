import {goalProgressCopy, loadOmiGoals, parseOmiGoals} from './legacyOmiGoals';
import type {OmiBackend} from './omiNativeTypes';

test('formats GET goal progress like Flutter raw current/target', () => {
  expect(goalProgressCopy(3, 10)).toBe('3/10');
  expect(goalProgressCopy(3.5, 10)).toBe('3.5/10');
  expect(goalProgressCopy(0, 0)).toBe('0/0');
});

test('parses GET goals titles and omits empty titles', () => {
  const rows = parseOmiGoals(
    JSON.stringify([
      {
        id: 'goal-read',
        title: 'Read 20 books',
        current_value: 3,
        target_value: 10,
      },
      {id: 'goal-empty', title: ' \t', current_value: 1, target_value: 2},
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

test('caps parsed GET goals at four after empty titles', () => {
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
  expect(rows.map(row => row.id)).toEqual(['g1', 'g2', 'g3', 'g4']);
});

test('does not omit a neighboring titled goal when stored metrics cannot project', () => {
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
        id: 'goal-object',
        title: 'Object metrics',
        current_value: {value: 1},
        target_value: 2,
      },
    ]),
  );
  expect(rows).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-string', title: 'Walk daily', current: 1.5, target: 4},
  ]);
});

test('fails closed for malformed GET goals', () => {
  expect(() => parseOmiGoals(JSON.stringify({id: 'goal-1'}))).toThrow();
  expect(() =>
    parseOmiGoals(
      JSON.stringify([
        {id: 'goal-1', title: 1, current_value: 1, target_value: 2},
      ]),
    ),
  ).toThrow();
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
    ]),
  });
  expect(await loadOmiGoals(backend)).toEqual([
    {id: 'goal-read', title: 'Read 20 books', current: 3, target: 10},
    {id: 'goal-string', title: 'Walk daily', current: 1.5, target: 4},
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
