import {
  loadOmiWebhookUrls,
  mergeWebhookUrl,
  parseOmiWebhookUrl,
} from './legacyOmiWebhookUrls';
import type {OmiBackend} from './omiNativeTypes';

function backendWith(
  responses: Record<string, {status: number; body: string | null}>,
): OmiBackend {
  return {
    request: async request => {
      const response = responses[request.path];
      if (response === undefined) {
        return {id: request.id, status: 404, body: null};
      }
      return {id: request.id, status: response.status, body: response.body};
    },
  };
}

test('parseOmiWebhookUrl names GET url and audio_bytes interval', () => {
  expect(
    parseOmiWebhookUrl('{"url":"https://example.test/a"}', 'memory_created'),
  ).toEqual({
    url: 'https://example.test/a',
    intervalSeconds: null,
  });
  expect(
    parseOmiWebhookUrl(
      '{"url":"  https://example.test/audio , 5  "}',
      'audio_bytes',
    ),
  ).toEqual({
    url: 'https://example.test/audio',
    intervalSeconds: '5',
  });
  expect(
    parseOmiWebhookUrl('{"url":"https://example.test/a,5"}', 'day_summary'),
  ).toEqual({
    url: 'https://example.test/a,5',
    intervalSeconds: null,
  });
  expect(parseOmiWebhookUrl('{"url":""}', 'memory_created')).toBeNull();
  expect(
    parseOmiWebhookUrl('{"url":" \t\n"}', 'realtime_transcript'),
  ).toBeNull();
  expect(parseOmiWebhookUrl('{"url":",5"}', 'audio_bytes')).toEqual({
    url: null,
    intervalSeconds: '5',
  });
  expect(
    parseOmiWebhookUrl('{"url":"https://example.test/a,abc"}', 'audio_bytes'),
  ).toEqual({
    url: 'https://example.test/a',
    intervalSeconds: null,
  });
});

test('parseOmiWebhookUrl omits malformed bodies', () => {
  expect(() => parseOmiWebhookUrl('[]', 'memory_created')).toThrow(
    'Omi webhook URL is malformed',
  );
  expect(() => parseOmiWebhookUrl('{"url":1}', 'memory_created')).toThrow(
    'Omi webhook URL is malformed',
  );
});

test('loadOmiWebhookUrls names GET rows and omits failures', async () => {
  expect(
    await loadOmiWebhookUrls(
      backendWith({
        '/v1/users/developer/webhook/memory_created': {
          status: 200,
          body: JSON.stringify({url: 'https://example.test/conversation'}),
        },
        '/v1/users/developer/webhook/realtime_transcript': {
          status: 200,
          body: JSON.stringify({url: 'https://example.test/transcript'}),
        },
        '/v1/users/developer/webhook/audio_bytes': {
          status: 200,
          body: JSON.stringify({url: 'https://example.test/audio,12'}),
        },
        '/v1/users/developer/webhook/day_summary': {
          status: 200,
          body: JSON.stringify({url: '  https://example.test/day  '}),
        },
      }),
    ),
  ).toEqual(
    new Map([
      [
        'memory_created',
        {url: 'https://example.test/conversation', intervalSeconds: null},
      ],
      [
        'realtime_transcript',
        {url: 'https://example.test/transcript', intervalSeconds: null},
      ],
      [
        'audio_bytes',
        {url: 'https://example.test/audio', intervalSeconds: '12'},
      ],
      ['day_summary', {url: 'https://example.test/day', intervalSeconds: null}],
    ]),
  );
  expect(
    await loadOmiWebhookUrls(
      backendWith({
        '/v1/users/developer/webhook/memory_created': {
          status: 404,
          body: null,
        },
        '/v1/users/developer/webhook/audio_bytes': {
          status: 200,
          body: '[]',
        },
      }),
    ),
  ).toEqual(new Map());
});

test('mergeWebhookUrl prefers sibling GET url over status url', () => {
  expect(
    mergeWebhookUrl(
      {type: 'memory_created', enabled: true, url: 'https://status.test/a'},
      new Map([
        [
          'memory_created',
          {url: 'https://example.test/conversation', intervalSeconds: null},
        ],
      ]),
    ),
  ).toEqual({
    enabled: true,
    url: 'https://example.test/conversation',
    intervalSeconds: null,
  });
  expect(
    mergeWebhookUrl(
      {type: 'memory_created', enabled: true, url: 'https://status.test/a'},
      new Map(),
    ),
  ).toEqual({
    enabled: true,
    url: 'https://status.test/a',
    intervalSeconds: null,
  });
});
