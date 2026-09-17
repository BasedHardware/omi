import {parseWebhookStatuses} from './desktopCloudClient';

test('parses GET webhook statuses without inventing omitted types', () => {
  expect(
    parseWebhookStatuses(
      {
        memory_created: true,
        realtime_transcript: false,
        audio_bytes: true,
        day_summary: false,
      },
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
    {type: 'day_summary', enabled: false, url: null},
  ]);
});

test('omits a GET webhook status entry that cannot project without hiding neighbors', () => {
  expect(
    parseWebhookStatuses(
      {
        memory_created: true,
        extra: 1,
        realtime_transcript: false,
        audio_bytes: true,
        day_summary: null,
        also: [true],
      },
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
  ]);
});

test('fails closed for a malformed GET webhook status body', () => {
  expect(() => parseWebhookStatuses([], 'Webhooks response')).toThrow(
    'Webhooks response is malformed',
  );
  expect(() => parseWebhookStatuses(null, 'Webhooks response')).toThrow(
    'Webhooks response is malformed',
  );
});

test('names Flutter UserWebhooksStatusResponse fromJson type-wrong GET memory_created instead of remapping to a Conversation Events chip', () => {
  const neighbor = {
    memory_created: true,
    realtime_transcript: false,
    audio_bytes: true,
    day_summary: false,
  };
  expect(parseWebhookStatuses(neighbor, 'Webhooks response')).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
    {type: 'day_summary', enabled: false, url: null},
  ]);
  expect(
    parseWebhookStatuses(
      {realtime_transcript: false, audio_bytes: true, day_summary: false},
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
    {type: 'day_summary', enabled: false, url: null},
  ]);
  expect(
    parseWebhookStatuses(
      {
        memory_created: null,
        realtime_transcript: false,
        audio_bytes: true,
        day_summary: false,
        extra: 1,
      },
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
    {type: 'day_summary', enabled: false, url: null},
  ]);
  expect(
    parseWebhookStatuses(
      {...neighbor, button_event: false},
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: null},
    {type: 'day_summary', enabled: false, url: null},
    {type: 'button_event', enabled: false, url: null},
  ]);
  for (const extra of [1, [], {}, 'x', {enabled: true}]) {
    expect(() =>
      parseWebhookStatuses(
        {...neighbor, memory_created: extra},
        'Webhooks response',
      ),
    ).toThrow('Webhooks response is malformed');
  }
  expect(() =>
    parseWebhookStatuses(
      {...neighbor, memory_created: {enabled: true, url: 'https://example.test/a'}},
      'Webhooks response',
    ),
  ).toThrow('Webhooks response is malformed');
  expect(() =>
    parseWebhookStatuses({...neighbor, audio_bytes: []}, 'Webhooks response'),
  ).toThrow('Webhooks response is malformed');
  expect(() =>
    parseWebhookStatuses({...neighbor, button_event: 1}, 'Webhooks response'),
  ).toThrow('Webhooks response is malformed');
  expect(() =>
    parseWebhookStatuses(
      {...neighbor, realtime_transcript: {}},
      'Webhooks response',
    ),
  ).toThrow('Webhooks response is malformed');
  expect(() =>
    parseWebhookStatuses({...neighbor, day_summary: 'x'}, 'Webhooks response'),
  ).toThrow('Webhooks response is malformed');
});
