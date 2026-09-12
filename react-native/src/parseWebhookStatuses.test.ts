import {parseWebhookStatuses} from './desktopCloudClient';

test('parses GET webhook statuses without inventing omitted types', () => {
  expect(
    parseWebhookStatuses(
      {
        memory_created: true,
        realtime_transcript: false,
        audio_bytes: {enabled: true, url: 'https://example.test/audio'},
        day_summary: {status: false},
      },
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: 'https://example.test/audio'},
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
        audio_bytes: {enabled: true, url: 'https://example.test/audio'},
        day_summary: null,
        also: [true],
      },
      'Webhooks response',
    ),
  ).toEqual([
    {type: 'memory_created', enabled: true, url: null},
    {type: 'realtime_transcript', enabled: false, url: null},
    {type: 'audio_bytes', enabled: true, url: 'https://example.test/audio'},
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
