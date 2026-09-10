import {
  loadOmiTaskIntegrations,
  parseOmiTaskIntegrations,
  taskIntegrationName,
  taskIntegrationRowCopy,
} from './legacyOmiTaskIntegrations';
import type {OmiBackend} from './omiNativeTypes';

test('names GET task integration keys like Flutter display names', () => {
  expect(taskIntegrationName('todoist')).toBe('Todoist');
  expect(taskIntegrationName('asana')).toBe('Asana');
  expect(taskIntegrationName('clickup')).toBe('ClickUp');
  expect(taskIntegrationName('google_tasks')).toBe('Google Tasks');
  expect(taskIntegrationName('apple_reminders')).toBe('Apple Reminders');
  expect(taskIntegrationName('trello')).toBe('Trello');
  expect(taskIntegrationName('monday')).toBe('Monday');
  expect(taskIntegrationName('linear')).toBe('linear');
});

test('formats GET task integration rows with Default only when selected', () => {
  expect(
    taskIntegrationRowCopy({key: 'todoist', name: 'Todoist', isDefault: true}),
  ).toBe('Todoist · Default');
  expect(
    taskIntegrationRowCopy({key: 'clickup', name: 'ClickUp', isDefault: false}),
  ).toBe('ClickUp');
});

test('parses GET connected task integrations and omits disconnected secrets', () => {
  const rows = parseOmiTaskIntegrations(
    JSON.stringify({
      integrations: {
        todoist: {connected: true, access_token: 'secret-todoist'},
        asana: {connected: false, access_token: 'secret-asana'},
        clickup: {connected: true},
        linear: {connected: true},
        ' \t': {connected: true},
      },
      default_app: 'todoist',
    }),
  );
  expect(rows).toEqual([
    {key: 'todoist', name: 'Todoist', isDefault: true},
    {key: 'clickup', name: 'ClickUp', isDefault: false},
    {key: 'linear', name: 'linear', isDefault: false},
  ]);
  expect(JSON.stringify(rows)).not.toContain('secret');
  expect(JSON.stringify(rows)).not.toContain('access_token');
});

test('omits empty GET task integrations and unknown defaults', () => {
  expect(parseOmiTaskIntegrations(JSON.stringify({integrations: {}}))).toEqual(
    [],
  );
  expect(
    parseOmiTaskIntegrations(
      JSON.stringify({
        integrations: {todoist: {connected: true}},
        default_app: 'asana',
      }),
    ),
  ).toEqual([{key: 'todoist', name: 'Todoist', isDefault: false}]);
});

test('fails closed for malformed GET task integrations', () => {
  expect(() => parseOmiTaskIntegrations(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiTaskIntegrations(
      JSON.stringify({integrations: [{connected: true}]}),
    ),
  ).toThrow();
  expect(() =>
    parseOmiTaskIntegrations(
      JSON.stringify({integrations: {todoist: {connected: 'true'}}}),
    ),
  ).toThrow();
  expect(() =>
    parseOmiTaskIntegrations(JSON.stringify({integrations: {todoist: true}})),
  ).toThrow();
  expect(() =>
    parseOmiTaskIntegrations(
      JSON.stringify({
        integrations: {todoist: {connected: true}},
        default_app: 1,
      }),
    ),
  ).toThrow();
});

test('loadOmiTaskIntegrations names resolved GET integrations and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'task-integrations',
    status: 200,
    body: JSON.stringify({
      integrations: {todoist: {connected: true, access_token: 'secret'}},
      default_app: 'todoist',
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiTaskIntegrations(backend)).toEqual([
    {key: 'todoist', name: 'Todoist', isDefault: true},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/task-integrations',
  });
  expect(
    request.mock.calls.some(
      call => call[0].path === '/v1/task-integrations/default',
    ),
  ).toBe(false);
  request.mockResolvedValueOnce({
    id: 'task-integrations',
    status: 404,
    body: null,
  });
  expect(await loadOmiTaskIntegrations(backend)).toEqual([]);
  request.mockResolvedValueOnce({
    id: 'task-integrations',
    status: 200,
    body: '{',
  });
  expect(await loadOmiTaskIntegrations(backend)).toEqual([]);
});
