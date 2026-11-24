import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

test('personas bootstrap disables flags while queuing analytics capture and identify', () => {
  const layout = readFileSync(new URL('../../app/layout.tsx', import.meta.url), 'utf8');
  const snippet = '!function' + layout.split('!function')[1].split('`')[0];
  const context = {
    document: {
      createElement: () => ({}),
      getElementsByTagName: () => [{ parentNode: { insertBefore() {} } }],
    },
  };
  context.window = context;
  vm.runInNewContext(snippet, context);
  assert.equal(context.posthog._i[0][1].advanced_disable_feature_flags, true);
  context.posthog.capture('Chat Message Sent');
  context.posthog.identify('test-user');
  assert.equal(context.posthog[0][0], 'capture');
  assert.equal(context.posthog[1][0], 'identify');
});
