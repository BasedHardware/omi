import assert from 'node:assert/strict';

import { assertFails, initializeTestEnvironment } from '@firebase/rules-unit-testing';
import { deleteDoc, doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';

const MEMORY_PROTECTED_COLLECTIONS = [
  'memory_items',
  'memory_operations',
  'memory_outbox',
  'memory_control',
  'memory_state',
  'memory_commits',
  'memory_evidence',
  'v3_compatibility_projection',
  'v3_compatibility_projection_items',
  'short_term_lifecycle_transitions',
];

const PROJECT_ID = process.env.GCLOUD_PROJECT || process.env.FIREBASE_PROJECT || 'demo-memory';

async function assertClientDeniedForProtectedCollection(db, collection) {
  const protectedDoc = doc(db, 'users', 'memory-emulator-user', collection, 'probe-doc');

  await assertFails(getDoc(protectedDoc));
  await assertFails(setDoc(protectedDoc, { collection, probe: true }));
  await assertFails(updateDoc(protectedDoc, { probe: false }));
  await assertFails(deleteDoc(protectedDoc));
}

async function assertClientDeniedForV3ControlReaderState(db) {
  const controlStateDoc = doc(db, 'users/memory-emulator-user/memory_control/state');
  const controlState = {
    uid: 'memory-emulator-user',
    schema_version: 1,
    mode: 'read',
    mode_epoch: 1,
    cutover_epoch: 1,
    account_generation: 50,
    fallback_projection_ready: true,
    persistent_memory_writes_started: true,
    writes_blocked: false,
    stage_gates: { shadow: 'passed', write: 'passed', read: 'passed' },
    grants: { omi_chat: { default_memory: true, archive: false } },
  };

  await assertFails(getDoc(controlStateDoc));
  await assertFails(setDoc(controlStateDoc, controlState));
  await assertFails(updateDoc(controlStateDoc, { mode_epoch: 2 }));
  await assertFails(deleteDoc(controlStateDoc));
}

async function assertClientDeniedForV3MemoryStateHead(db) {
  const stateHeadDoc = doc(db, 'users/memory-emulator-user/memory_state/head');
  const stateHead = {
    schema_version: 1,
    uid: 'memory-emulator-user',
    source: 'memory_state_head',
    account_generation: 50,
    head_commit_id: 'commit-client-forbidden',
    commit_sequence: 50,
  };

  await assertFails(getDoc(stateHeadDoc));
  await assertFails(setDoc(stateHeadDoc, stateHead));
  await assertFails(updateDoc(stateHeadDoc, { account_generation: 51 }));
  await assertFails(deleteDoc(stateHeadDoc));
}

async function assertClientDeniedForV3MemoryApplyControl(db) {
  const applyControlDoc = doc(db, 'users/memory-emulator-user/memory_state/apply_control');
  const applyControl = {
    uid: 'memory-emulator-user',
    head_commit_id: 'head0',
    account_generation: 50,
    source_generation: 1,
    commit_sequence: 0,
  };

  await assertFails(getDoc(applyControlDoc));
  await assertFails(setDoc(applyControlDoc, applyControl));
  await assertFails(updateDoc(applyControlDoc, { source_generation: 2 }));
  await assertFails(deleteDoc(applyControlDoc));
}

async function assertClientCannotSelfGrantAppKeyMemoryAccess(db) {
  const grantDoc = doc(db, 'users/memory-emulator-user/memory_control/app_key_memory_grants');
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

async function assertClientDeniedForV3CanaryApprovalSource(db) {
  const approvalDoc = doc(db, 'system/v3_canary_approvals/routes/get_v3_memories');
  const approvalArtifact = {
    route_scope: 'GET /v3/memories',
    approval_claimed: false,
    owner_groups: ['product_privacy_ops', 'memory_platform_oncall'],
    probe: 'client-forbidden',
  };

  await assertFails(getDoc(approvalDoc));
  await assertFails(setDoc(approvalDoc, approvalArtifact));
  await assertFails(updateDoc(approvalDoc, { approval_claimed: true }));
  await assertFails(deleteDoc(approvalDoc));
}

async function assertAdminCanReadV3CanaryApprovalSource(testEnv) {
  const approvalArtifact = {
    route_scope: 'GET /v3/memories',
    approval_claimed: false,
    owner_groups: ['product_privacy_ops', 'memory_platform_oncall'],
    probe: 'admin-service-principal-read-fixture',
  };

  await testEnv.withSecurityRulesDisabled(async (adminContext) => {
    const approvalDoc = doc(adminContext.firestore(), 'system/v3_canary_approvals/routes/get_v3_memories');
    await setDoc(approvalDoc, approvalArtifact);
    const snapshot = await getDoc(approvalDoc);
    assert.equal(snapshot.exists(), true);
    assert.equal(snapshot.data().route_scope, 'GET /v3/memories');
    await deleteDoc(approvalDoc);
  });
}

const testEnv = await initializeTestEnvironment({ projectId: PROJECT_ID });

try {
  const db = testEnv.authenticatedContext('memory-emulator-user').firestore();

  for (const collection of MEMORY_PROTECTED_COLLECTIONS) {
    await assertClientDeniedForProtectedCollection(db, collection);
  }
  await assertClientDeniedForV3ControlReaderState(db);
  await assertClientDeniedForV3MemoryStateHead(db);
  await assertClientDeniedForV3MemoryApplyControl(db);
  await assertClientCannotSelfGrantAppKeyMemoryAccess(db);
  await assertClientDeniedForV3CanaryApprovalSource(db);
  await assertAdminCanReadV3CanaryApprovalSource(testEnv);

  assert.equal(MEMORY_PROTECTED_COLLECTIONS.length, 10);
  console.log(
    `PASS: signed-in client read/write denial asserted for ${MEMORY_PROTECTED_COLLECTIONS.length} memory collections, users/{uid}/memory_control/state, users/{uid}/memory_state/head, users/{uid}/memory_state/apply_control, memory app/key memory grant self-grant path, and system/v3_canary_approvals/routes/get_v3_memories; Admin-context read fixture proved for canary approval source`,
  );
} finally {
  await testEnv.cleanup();
}
