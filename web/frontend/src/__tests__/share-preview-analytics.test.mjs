import assert from 'node:assert/strict';
import test from 'node:test';
import {
  previewAttribution,
  previewDestination,
} from '../lib/share-preview-analytics.mjs';

test('classifies common destination preview agents without raw agent properties', () => {
  assert.equal(previewDestination('WhatsApp/2.0'), 'whatsapp');
  assert.equal(previewDestination('Slackbot-LinkExpanding 1.0'), 'slack');
  assert.equal(previewDestination('TelegramBot'), 'telegram');
  assert.equal(previewDestination('facebookexternalhit/1.1'), 'meta');
  assert.equal(previewDestination('Discordbot/2.0'), 'discord');
  assert.equal(previewDestination('Googlebot'), 'search');
  assert.equal(previewDestination('Mozilla/5.0 iPhone'), null);
});

test('allows only source enum and random share id', () => {
  assert.deepEqual(previewAttribution(new URLSearchParams('s=ios&sid=abc12345_X')), {
    s: 'ios',
    share_id: 'abc12345_X',
  });
  assert.deepEqual(
    previewAttribution(new URLSearchParams('s=email@example.com&sid=email@example.com')),
    {
      s: 'unknown',
      share_id: undefined,
    },
  );
});
