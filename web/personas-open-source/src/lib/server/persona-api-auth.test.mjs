import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PersonaAuthenticationError,
  assertPersonaUidMatch,
  resolvePersonaIdentity,
  resolvePersonaOwnerIdentity,
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

test('persona ownership keeps verified anonymous UIDs (chat tier does not)', async () => {
  const options = {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({ users: [{ localId: 'anonymous-uid', providerUserInfo: [] }] }),
  };

  // The persona creation flow signs visitors in anonymously and writes the
  // persona under that UID; 401ing it drops their plugins and facts silently.
  const owner = await resolvePersonaOwnerIdentity('Bearer anonymous-token', options);
  assert.deepEqual(owner, { uid: 'anonymous-uid' });
  assert.equal(assertPersonaUidMatch(owner, 'anonymous-uid'), 'anonymous-uid');

  // The chat tier still collapses anonymous users to the free lane.
  assert.equal(await resolvePersonaIdentity('Bearer anonymous-token', options), null);
});

test('persona ownership still rejects another user uid', async () => {
  const owner = await resolvePersonaOwnerIdentity('Bearer anonymous-token', {
    firebaseApiKey: 'firebase-public-key',
    fetchImpl: async () =>
      Response.json({ users: [{ localId: 'anonymous-uid', providerUserInfo: [] }] }),
  });
  assert.throws(
    () => assertPersonaUidMatch(owner, 'someone-else'),
    PersonaAuthenticationError,
  );
});

test('persona ownership fails closed without a token', async () => {
  assert.equal(await resolvePersonaOwnerIdentity(null), null);
  await assert.rejects(
    resolvePersonaOwnerIdentity('Bearer bad-token', {
      firebaseApiKey: 'firebase-public-key',
      fetchImpl: async () => new Response('{}', { status: 401 }),
    }),
    PersonaAuthenticationError,
  );
});

test('persona ownership rejects a disabled account', async () => {
  await assert.rejects(
    resolvePersonaOwnerIdentity('Bearer disabled-token', {
      firebaseApiKey: 'firebase-public-key',
      fetchImpl: async () =>
        Response.json({ users: [{ localId: 'uid', disabled: true }] }),
    }),
    PersonaAuthenticationError,
  );
});
