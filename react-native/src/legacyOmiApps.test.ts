import {attachOmiChatAppNames, loadOmiApps, parseOmiApp} from './legacyOmiApps';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET app name and description and omits empty or deleted apps', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        description: 'Saves notes from calls',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes', description: 'Saves notes from calls'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', description: ' \t'}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes'),
  ).toEqual({name: 'Notes'});
  expect(() =>
    parseOmiApp(JSON.stringify({id: 'notes', name: ' \t'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiApp(JSON.stringify({id: 'other', name: 'Notes'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', deleted: true}),
      'notes',
    ),
  ).toThrow();
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', description: 1}),
      'notes',
    ),
  ).toThrow();
});

test('parseOmiApp keeps GET http(s) images and omits relative or unsafe URLs', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'https://cdn.example.test/notes.png',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes', image: 'https://cdn.example.test/notes.png'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        description: 'Saves notes from calls',
        image: '  HTTP://cdn.example.test/notes.png  ',
      }),
      'notes',
    ),
  ).toEqual({
    name: 'Notes',
    description: 'Saves notes from calls',
    image: 'HTTP://cdn.example.test/notes.png',
  });
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: '/assets/apps/notes.png',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'javascript:https://evil.test',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'data:image/png;base64,abc',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', image: ' \t'}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', image: 1}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
});

test('does not omit a neighboring named chat app when GET lists more than twenty unique plugin ids', async () => {
  const unique = Array.from({length: 21}, (_, i) => `app-${i + 1}`);
  const request = jest.fn(async (input: {path: string}) => {
    const id = decodeURIComponent(input.path.replace('/v1/apps/', ''));
    return {
      id: 'app',
      status: 200,
      body: JSON.stringify({id, name: `Name ${id}`}),
    };
  });
  const backend = {request} as unknown as OmiBackend;
  const apps = await loadOmiApps(backend, [
    '  ',
    unique[0],
    unique[0],
    ...unique.slice(1),
  ]);
  expect([...apps.keys()]).toEqual(unique);
  expect(request).toHaveBeenCalledTimes(21);
  expect(apps.get('app-21')).toEqual({name: 'Name app-21'});
});

test('loadOmiApps names resolved GET apps and omits failures', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          description: 'Saves notes from calls',
          image: 'https://cdn.example.test/notes.png',
        }),
      };
    }
    if (input.path === '/v1/apps/missing') {
      return {id: 'app', status: 404, body: '{}'};
    }
    return {id: 'app', status: 200, body: '{'};
  });
  const backend = {request} as unknown as OmiBackend;
  const apps = await loadOmiApps(backend, ['notes', 'missing', 'broken']);
  expect(apps.get('notes')).toEqual({
    name: 'Notes',
    description: 'Saves notes from calls',
    image: 'https://cdn.example.test/notes.png',
  });
  expect(apps.has('missing')).toBe(false);
  expect(apps.has('broken')).toBe(false);
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
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      description: 'Saves notes from calls',
      image: 'https://cdn.example.test/notes.png',
    }),
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
  expect(messages[0]).not.toHaveProperty('appDescription');
  expect(messages[0]).not.toHaveProperty('appImage');
  expect(messages[0]).not.toHaveProperty('image');
  expect(JSON.stringify(messages[0])).not.toContain('Saves notes from calls');
  expect(JSON.stringify(messages[0])).not.toContain(
    'https://cdn.example.test/notes.png',
  );
  expect(messages[1]).toEqual(expect.objectContaining({appId: 'ghost'}));
  expect(messages[1]).not.toHaveProperty('appName');
  expect(messages[2]).not.toHaveProperty('appId');
  expect(messages[2]).not.toHaveProperty('appName');
  expect(request).toHaveBeenCalledTimes(2);
});
