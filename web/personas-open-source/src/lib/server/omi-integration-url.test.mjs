import assert from 'node:assert/strict';
import test from 'node:test';

import { integrationMemoriesUrl } from './omi-integration-url.mjs';

test('store-facts URL keeps a normal uid and app id intact', () => {
  assert.equal(
    integrationMemoriesUrl('persona-app', 'user-abc123'),
    'https://api.omi.me/v2/integrations/persona-app/user/memories?uid=user-abc123',
  );
});

test('store-facts URL cannot be split by a uid carrying query delimiters', () => {
  const url = integrationMemoriesUrl('persona-app', 'victim&admin=1');
  assert.equal(
    url,
    'https://api.omi.me/v2/integrations/persona-app/user/memories?uid=victim%26admin%3D1',
  );
  const parsed = new URL(url);
  assert.equal(parsed.searchParams.get('uid'), 'victim&admin=1');
  assert.equal(parsed.searchParams.get('admin'), null);
});

test('store-facts URL cannot be cut short by a fragment marker', () => {
  const parsed = new URL(integrationMemoriesUrl('persona-app', 'user#frag'));
  assert.equal(parsed.searchParams.get('uid'), 'user#frag');
  assert.equal(parsed.pathname, '/v2/integrations/persona-app/user/memories');
});

test('store-facts URL keeps an app id from altering the path', () => {
  const parsed = new URL(integrationMemoriesUrl('app/extra', 'u1'));
  assert.equal(parsed.pathname, '/v2/integrations/app%2Fextra/user/memories');
});
