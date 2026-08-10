import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PersonaAuthenticationError,
  assertPersonaUidMatch,
} from './persona-chat-gateway.mjs';

test('assertPersonaUidMatch returns uid when identity matches request', () => {
  assert.equal(assertPersonaUidMatch({ uid: 'user-1' }, 'user-1'), 'user-1');
});

test('assertPersonaUidMatch rejects null/anonymous identity', () => {
  assert.throws(() => assertPersonaUidMatch(null, 'user-1'), PersonaAuthenticationError);
});

test('assertPersonaUidMatch rejects uid mismatch', () => {
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, 'attacker'),
    PersonaAuthenticationError,
  );
});

test('assertPersonaUidMatch rejects missing requested uid', () => {
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, ''),
    PersonaAuthenticationError,
  );
  assert.throws(
    () => assertPersonaUidMatch({ uid: 'user-1' }, undefined),
    PersonaAuthenticationError,
  );
});
