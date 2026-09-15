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
  ).toEqual({name: 'Notes', description: ' \t'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', description: ''}),
      'notes',
    ),
  ).toEqual({name: 'Notes', description: ''});
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes'),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: ' \t'}), 'notes'),
  ).toEqual({name: ' \t'});
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: ''}), 'notes'),
  ).toEqual({name: ''});
  expect(() =>
    parseOmiApp(JSON.stringify({id: 'notes'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiApp(JSON.stringify({id: 'notes', name: 1}), 'notes'),
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

test('parseOmiApp names Flutter App.fromGenerated padded GET id instead of remapping to a catalog match', () => {
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes'),
  ).toEqual({name: 'Notes'});
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: '  notes  ', name: 'Notes'}),
      'notes',
    ),
  ).toThrow();
  expect(() =>
    parseOmiApp(JSON.stringify({id: 'notes ', name: 'Notes'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: '\u0085notes', name: 'Notes'}),
      'notes',
    ),
  ).toThrow();
  expect(() =>
    parseOmiApp(JSON.stringify({id: ' \t', name: 'Notes'}), 'notes'),
  ).toThrow();
  expect(() =>
    parseOmiApp(JSON.stringify({id: '', name: 'Notes'}), 'notes'),
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
  });
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'HTTPS://cdn.example.test/notes.png',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'https://cdn.example.test/notes.png ',
      }),
      'notes',
    ),
  ).toEqual({
    name: 'Notes',
    image: 'https://cdn.example.test/notes.png ',
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

test('parseOmiApp names Flutter getImageUrl padded GET http instead of remapping to a CDN chip', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: '  https://cdn.example.test/notes.png  ',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        image: 'HTTP://cdn.example.test/notes.png',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
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

test('loadOmiApps names Flutter App.fromGenerated padded GET id instead of remapping to a catalog name', async () => {
  const catalog = (id: string) =>
    jest.fn(async () => ({
      id: 'app',
      status: 200,
      body: JSON.stringify({id, name: 'Notes'}),
    }));
  const padded = catalog('  notes  ');
  expect(
    (
      await loadOmiApps(
        {request: padded} as unknown as OmiBackend,
        ['notes'],
      )
    ).has('notes'),
  ).toBe(false);
  const trailing = catalog('notes ');
  expect(
    (
      await loadOmiApps(
        {request: trailing} as unknown as OmiBackend,
        ['notes'],
      )
    ).has('notes'),
  ).toBe(false);
  const nextLine = catalog('\u0085notes');
  expect(
    (
      await loadOmiApps(
        {request: nextLine} as unknown as OmiBackend,
        ['notes'],
      )
    ).has('notes'),
  ).toBe(false);
});

test('attachOmiChatAppNames keeps unresolved app ids off the named chrome', async () => {
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
    if (input.path === '/v1/apps/relative') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'relative',
          name: 'Relative',
          image: '/assets/apps/notes.png',
        }),
      };
    }
    return {id: 'app', status: 404, body: '{}'};
  });
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
    {
      id: 'ai-4',
      text: 'Relative icon.',
      sender: 'ai',
      createdAt: 4,
      generationOutcome: null,
      appId: 'relative',
    },
  ]);
  expect(messages[0]).toMatchObject({
    appId: 'notes',
    appName: 'Notes',
    appImage: 'https://cdn.example.test/notes.png',
  });
  expect(messages[0]).not.toHaveProperty('appDescription');
  expect(messages[0]).not.toHaveProperty('image');
  expect(JSON.stringify(messages[0])).not.toContain('Saves notes from calls');
  expect(JSON.stringify(messages[0])).not.toContain(
    'raw.githubusercontent.com',
  );
  expect(messages[1]).toEqual(expect.objectContaining({appId: 'ghost'}));
  expect(messages[1]).not.toHaveProperty('appName');
  expect(messages[1]).not.toHaveProperty('appImage');
  expect(messages[2]).not.toHaveProperty('appId');
  expect(messages[2]).not.toHaveProperty('appName');
  expect(messages[2]).not.toHaveProperty('appImage');
  expect(messages[3]).toMatchObject({appId: 'relative', appName: 'Relative'});
  expect(messages[3]).not.toHaveProperty('appImage');
  expect(JSON.stringify(messages[3])).not.toContain(
    'raw.githubusercontent.com',
  );
  expect(request).toHaveBeenCalledTimes(3);
});

test('attachOmiChatAppNames names Flutter AIMessage padded GET plugin_id instead of remapping to a catalog name', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          image: 'https://cdn.example.test/notes.png',
        }),
      };
    }
    return {id: 'app', status: 404, body: '{}'};
  });
  const backend = {request} as unknown as OmiBackend;
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'exact',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
    {
      id: 'padded',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 2,
      generationOutcome: null,
      appId: '  notes  ',
    },
    {
      id: 'trailing',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 3,
      generationOutcome: null,
      appId: 'notes ',
    },
    {
      id: 'next-line',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 4,
      generationOutcome: null,
      appId: '\u0085notes',
    },
  ]);
  expect(messages[0]).toMatchObject({
    appId: 'notes',
    appName: 'Notes',
    appImage: 'https://cdn.example.test/notes.png',
  });
  expect(messages[1]).toEqual(
    expect.objectContaining({appId: '  notes  '}),
  );
  expect(messages[1]).not.toHaveProperty('appName');
  expect(messages[1]).not.toHaveProperty('appImage');
  expect(messages[2]).toEqual(expect.objectContaining({appId: 'notes '}));
  expect(messages[2]).not.toHaveProperty('appName');
  expect(messages[3]).toEqual(
    expect.objectContaining({appId: '\u0085notes'}),
  );
  expect(messages[3]).not.toHaveProperty('appName');
});
