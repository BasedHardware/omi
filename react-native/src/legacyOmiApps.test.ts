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

test('old apps name Flutter App.fromGenerated padded GET created_at instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        created_at: '2026-09-07T00:00:00.000Z',
        installs: '12',
        rating_avg: '4.5',
        rating_count: '12',
        price: '9.99',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        created_at: '2026-09-07T00:00:00.000Z',
        installs: 12,
        rating_avg: 4.5,
        rating_count: 12,
        price: 9.99,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes')).toEqual({
    name: 'Notes',
  });
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        created_at: null,
        installs: null,
        rating_avg: null,
        rating_count: null,
        price: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const created_at of [
    '  2026-09-07T00:00:00.000Z  ',
    '2026-09-07T00:00:00.000Z ',
    '  2026-09-07T00:00:00.000Z',
    '2026-09-07T00:00:00.000Z\n',
    '\u00852026-09-07T00:00:00.000Z',
  ]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', created_at}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', installs: '  12  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', rating_avg: '  4.5  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', price: '  9.99  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', score: '  1.5  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', money_made: '  2.5  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', usage_count: '  7  '}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
});

test('old apps name Flutter App.fromGenerated type-wrong GET created_at instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        created_at: '2026-09-07T00:00:00.000Z',
        installs: '12',
        rating_avg: '4.5',
        rating_count: '12',
        price: '9.99',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        created_at: null,
        installs: null,
        rating_avg: null,
        rating_count: null,
        price: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const created_at of ['', 'not-a-date', 1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', created_at}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
  for (const installs of ['', 'abc', true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', installs}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', rating_avg: ''}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', rating_avg: true}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', usage_count: ''}),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
});

test('old apps name Flutter App.fromGenerated type-wrong GET author instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        author: 'Ada',
        category: 'productivity',
        status: 'approved',
        uid: 'user-1',
        username: 'ada',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        author: null,
        category: null,
        chat_prompt: null,
        status: null,
        uid: null,
        username: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        author: '',
        category: '  productivity  ',
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', author: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', category: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', status: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', uid: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', username: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', chat_prompt: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET image instead of remapping to a catalog name', () => {
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
      JSON.stringify({id: 'notes', name: 'Notes', image: null}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes'}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', image: ''}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
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
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', image: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET proactive_notification instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: ['user']},
        twitter: {handle: 'notes'},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: null,
        twitter: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes'}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: 1},
        twitter: {},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          proactive_notification: extra,
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', twitter: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET user_review instead of remapping to a catalog name', () => {
  const review = {
    rated_at: '2026-09-07T00:00:00.000Z',
    review: 'Great',
    score: 5,
    uid: 'user-1',
  };
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: review,
        external_integration: {mcp_oauth_tokens: {token: 'x'}},
        chat_tools: [
          {
            name: 'search',
            description: 'Search notes',
            endpoint: '/s',
            parameters: {q: 'notes'},
          },
        ],
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: null,
        external_integration: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes'),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: {},
        reviews: 1,
        external_integration: {mcp_oauth_tokens: {}},
        chat_tools: [
          {
            name: 'search',
            description: 'Search notes',
            endpoint: '/s',
            parameters: {},
          },
        ],
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({id: 'notes', name: 'Notes', user_review: extra}),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          reviews: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: extra,
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {mcp_oauth_tokens: extra},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          chat_tools: [
            {
              name: 'search',
              description: 'Search notes',
              endpoint: '/s',
              parameters: extra,
            },
          ],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET chat_tools item instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        chat_tools: [
          {
            name: 'search',
            description: 'Search notes',
            endpoint: '/s',
          },
        ],
        external_integration: {
          actions: [{action: 'create'}],
          auth_steps: [{name: 'Login', url: 'https://example.test'}],
        },
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        chat_tools: 1,
        external_integration: {actions: 1, auth_steps: 1},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        chat_tools: [{}],
        external_integration: {actions: [{}], auth_steps: [{}]},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          chat_tools: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {actions: [extra]},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {auth_steps: [extra]},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET capabilities item instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        capabilities: ['chat'],
        connected_accounts: ['google'],
        thumbnail_urls: ['https://cdn.example.test/notes.png'],
        thumbnails: ['notes'],
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        capabilities: 1,
        connected_accounts: 1,
        thumbnail_urls: 1,
        thumbnails: 1,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        capabilities: null,
        connected_accounts: null,
        thumbnail_urls: [],
        thumbnails: [],
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          capabilities: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          connected_accounts: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          thumbnail_urls: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          thumbnails: [extra],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET scopes item instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: ['user']},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: 1},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: null},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {scopes: []},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        proactive_notification: {},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, []]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          proactive_notification: {scopes: [extra]},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated type-wrong GET webhook_url instead of remapping to a catalog name', () => {
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        external_integration: {
          webhook_url: 'https://example.test/hook',
          app_home_url: 'https://example.test',
          chat_messages_target: 'app',
        },
        chat_tools: [
          {
            name: 'search',
            description: 'Search notes',
            endpoint: 'https://example.test/search',
            method: 'POST',
            transport: 'streamable_http',
          },
        ],
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        external_integration: null,
        chat_tools: null,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        external_integration: {
          webhook_url: '',
          app_home_url: '  https://example.test  ',
        },
        chat_tools: 1,
        chat_messages_enabled: 1,
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {webhook_url: extra},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {chat_messages_target: extra},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          chat_tools: [{name: extra, description: 'Search', endpoint: '/s'}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          chat_tools: [{name: 'search', description: extra, endpoint: '/s'}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {actions: [{action: extra}]},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          external_integration: {auth_steps: [{name: 'Login', url: extra}]},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
});

test('old apps name Flutter App.fromGenerated padded GET reviews rated_at instead of remapping to a catalog name', () => {
  const review = {
    rated_at: '2026-09-07T00:00:00.000Z',
    review: 'Great',
    score: '5',
    uid: 'user-1',
  };
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        reviews: [review],
        user_review: {...review, score: 5},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', reviews: null, user_review: null}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(parseOmiApp(JSON.stringify({id: 'notes', name: 'Notes'}), 'notes')).toEqual({
    name: 'Notes',
  });
  for (const rated_at of [
    '  2026-09-07T00:00:00.000Z  ',
    '2026-09-07T00:00:00.000Z ',
    '  2026-09-07T00:00:00.000Z',
    '2026-09-07T00:00:00.000Z\n',
    '\u00852026-09-07T00:00:00.000Z',
  ]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          reviews: [{...review, rated_at}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        reviews: [{...review, score: '  5  '}],
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        reviews: [
          {...review, responded_at: '  2026-09-07T00:00:00.000Z  '},
        ],
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: {...review, rated_at: '  2026-09-07T00:00:00.000Z  '},
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: {...review, score: '  5  '},
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
});

test('old apps name Flutter App.fromGenerated type-wrong GET reviews rated_at instead of remapping to a catalog name', () => {
  const review = {
    rated_at: '2026-09-07T00:00:00.000Z',
    review: 'Great',
    score: '5',
    uid: 'user-1',
  };
  expect(
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        reviews: [review],
        user_review: {...review, score: 5},
      }),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  expect(
    parseOmiApp(
      JSON.stringify({id: 'notes', name: 'Notes', reviews: null, user_review: null}),
      'notes',
    ),
  ).toEqual({name: 'Notes'});
  for (const rated_at of ['', 'not-a-date', 1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          reviews: [{...review, rated_at}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        reviews: [{...review, score: ''}],
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  expect(() =>
    parseOmiApp(
      JSON.stringify({
        id: 'notes',
        name: 'Notes',
        user_review: {...review, rated_at: 1},
      }),
      'notes',
    ),
  ).toThrow('Omi app is malformed');
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          reviews: [{...review, review: extra}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          reviews: [{...review, uid: extra}],
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          user_review: {...review, username: extra},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
    expect(() =>
      parseOmiApp(
        JSON.stringify({
          id: 'notes',
          name: 'Notes',
          user_review: {...review, response: extra},
        }),
        'notes',
      ),
    ).toThrow('Omi app is malformed');
  }
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

test('old apps name Flutter App.fromGenerated type-wrong GET created_at instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      created_at: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET author instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      author: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET image instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      image: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET proactive_notification instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      proactive_notification: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET twitter instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      twitter: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET user_review instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      user_review: 1,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET mcp_oauth_tokens instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      external_integration: {mcp_oauth_tokens: 1},
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET chat_tools item instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      chat_tools: [1],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET capabilities item instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      capabilities: [1],
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET scopes item instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      proactive_notification: {scopes: [1]},
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});

test('old apps name Flutter App.fromGenerated type-wrong GET webhook_url instead of attaching a catalog name', async () => {
  const request = jest.fn(async () => ({
    id: 'app',
    status: 200,
    body: JSON.stringify({
      id: 'notes',
      name: 'Notes',
      external_integration: {webhook_url: 1},
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiApps(backend, ['notes'])).has('notes')).toBe(false);
  const messages = await attachOmiChatAppNames(backend, [
    {
      id: 'ai-1',
      text: 'Saved.',
      sender: 'ai',
      createdAt: 1,
      generationOutcome: null,
      appId: 'notes',
    },
  ]);
  expect(messages[0]).toEqual(expect.objectContaining({appId: 'notes'}));
  expect(messages[0]).not.toHaveProperty('appName');
});
