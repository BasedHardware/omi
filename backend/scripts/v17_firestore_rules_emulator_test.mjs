import assert from 'node:assert/strict';

import { assertFails, initializeTestEnvironment } from '@firebase/rules-unit-testing';
import { deleteDoc, doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';

const V17_PROTECTED_COLLECTIONS = [
  'memory_items',
  'memory_operations',
  'memory_outbox',
  'memory_control',
  'memory_state',
  'memory_commits',
  'memory_evidence',
  'short_term_lifecycle_transitions',
];

const PROJECT_ID = process.env.GCLOUD_PROJECT || process.env.FIREBASE_PROJECT || 'demo-v17-memory';

async function assertClientDeniedForProtectedCollection(db, collection) {
  const protectedDoc = doc(db, 'users', 'v17-emulator-user', collection, 'probe-doc');

  await assertFails(getDoc(protectedDoc));
  await assertFails(setDoc(protectedDoc, { collection, probe: true }));
  await assertFails(updateDoc(protectedDoc, { probe: false }));
  await assertFails(deleteDoc(protectedDoc));
}

async function assertClientCannotSelfGrantV17AppKeyMemoryAccess(db) {
  const grantDoc = doc(db, 'users/v17-emulator-user/memory_control/v17_app_key_memory_grants');
  const selfGrant = {
    grants: {
      developer_api: {
        apps: {
          'client-app': {
            keys: {
              'client-key': {
                enabled: true,
                scopes: ['memories.read', 'memories.archive.read', 'memories.write'],
                default_read: true,
                archive_read: true,
                write: true,
                probe: 'client-self-grant',
              },
            },
          },
        },
      },
    },
  };

  // Contract path: grants.developer_api.apps.client-app.keys.client-key.
  // Firestore client rules must deny creating/updating this server-owned grant
  // document even when a signed-in client tries to grant itself all scopes.
  await assertFails(getDoc(grantDoc));
  await assertFails(setDoc(grantDoc, selfGrant));
  await assertFails(updateDoc(grantDoc, selfGrant));
  await assertFails(deleteDoc(grantDoc));
}

const testEnv = await initializeTestEnvironment({ projectId: PROJECT_ID });

try {
  const db = testEnv.authenticatedContext('v17-emulator-user').firestore();

  for (const collection of V17_PROTECTED_COLLECTIONS) {
    await assertClientDeniedForProtectedCollection(db, collection);
  }
  await assertClientCannotSelfGrantV17AppKeyMemoryAccess(db);

  assert.equal(V17_PROTECTED_COLLECTIONS.length, 8);
  console.log(
    `PASS: signed-in client read/write denial asserted for ${V17_PROTECTED_COLLECTIONS.length} V17 collections and V17 app/key memory grant self-grant path`,
  );
} finally {
  await testEnv.cleanup();
}
