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

const testEnv = await initializeTestEnvironment({ projectId: PROJECT_ID });

try {
  const db = testEnv.authenticatedContext('v17-emulator-user').firestore();

  for (const collection of V17_PROTECTED_COLLECTIONS) {
    await assertClientDeniedForProtectedCollection(db, collection);
  }

  assert.equal(V17_PROTECTED_COLLECTIONS.length, 8);
  console.log(
    `PASS: signed-in client read/write denial asserted for ${V17_PROTECTED_COLLECTIONS.length} V17 collections`,
  );
} finally {
  await testEnv.cleanup();
}
