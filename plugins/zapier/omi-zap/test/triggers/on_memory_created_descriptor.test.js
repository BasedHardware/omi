// Hermetic descriptor checks for the on_memory_created hook trigger.
//
// `performSubscribe`/`performUnsubscribe` are declarative request descriptors
// consumed verbatim by zapier-platform-core, so the descriptor shape IS the
// behavior at this seam: the backend `DELETE /zapier/trigger/subscribe`
// handler requires `uid` as a query parameter and 422s without it, which left
// every unsubscribe failing and subscriptions leaking. Run with `node --test`.

const test = require('node:test');
const assert = require('node:assert/strict');

const trigger = require('../../triggers/on_memory_created.js');
const { performSubscribe, performUnsubscribe } = trigger.operation;

test('unsubscribe sends the auth uid so the backend can resolve the subscriber', () => {
  assert.equal(performUnsubscribe.params?.uid, '{{bundle.authData.uid}}');
});

test('unsubscribe keeps the DELETE shape the backend expects', () => {
  assert.equal(performUnsubscribe.method, 'DELETE');
  assert.equal(
    performUnsubscribe.url,
    'https://based-hardware--plugins-api.modal.run/zapier/trigger/subscribe',
  );
  assert.deepEqual(performUnsubscribe.body, { target_url: '{{bundle.targetUrl}}' });
});

test('subscribe still carries the uid parameter', () => {
  assert.equal(performSubscribe.params?.uid, '{{bundle.authData.uid}}');
  assert.equal(performSubscribe.method, 'POST');
});
