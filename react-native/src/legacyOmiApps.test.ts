import {
  attachOmiChatAppNames,
  loadOmiAppNames,
  parseOmiAppName,
} from './legacyOmiApps';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET app name and omits empty or deleted apps', () => {
  expect(
    parseOmiAppName(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes'),
  ).toBe('Notes');
  expect(() =>
    parseOmiAppName(JSON.stringify({id: 'notes', name: ' \t'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiAppName(JSON.stringify({id: 'other', name: 'Notes'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiAppName(
      JSON.stringify({id: 'notes', name: 'Notes', deleted: true}),
      'notes',
    ),
  ).toThrow();
});

test('loadOmiAppNames names resolved GET apps and omits failures', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({id: 'notes', name: 'Notes'}),
      };
    }
    if (input.path === '/v1/apps/missing') {
      return {id: 'app', status: 404, body: '{}'};
    }
    return {id: 'app', status: 200, body: '{'};
  });
  const backend = {request} as unknown as OmiBackend;
  const names = await loadOmiAppNames(backend, ['notes', 'missing', 'broken']);
  expect(names.get('notes')).toBe('Notes');
  expect(names.has('missing')).toBe(false);
  expect(names.has('broken')).toBe(false);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/apps/notes',
  });
});

test('attachOmiChatAppNames keeps unresolved app ids off the named chrome', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({id: 'notes', name: 'Notes'}),
  }));
  const backend = {request} as unknown as OmiBackend;
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
    {
      id: 'ai-2',
      text: 'Unknown plugin.',
      sender: 'ai',
      createdAt: 2,
      generationOutcome: null,
      appId: 'ghost',
    },
    {
      id: 'ai-3',
      text: 'Plain.',
      sender: 'ai',
      createdAt: 3,
      generationOutcome: null,
    },
  ]);
  expect(messages[0]).toMatchObject({appId: 'notes', appName: 'Notes'});
  expect(messages[1]).toEqual(expect.objectContaining({appId: 'ghost'}));
  expect(messages[1]).not.toHaveProperty('appName');
  expect(messages[2]).not.toHaveProperty('appId');
  expect(messages[2]).not.toHaveProperty('appName');
  expect(request).toHaveBeenCalledTimes(2);
});
