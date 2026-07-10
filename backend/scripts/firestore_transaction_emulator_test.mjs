import assert from 'node:assert/strict';

const PROJECT_ID = process.env.GCLOUD_PROJECT || process.env.FIREBASE_PROJECT || 'demo-memory';
const EMULATOR_HOST = process.env.FIRESTORE_EMULATOR_HOST || '127.0.0.1:8080';
const BASE_URL = `http://${EMULATOR_HOST}/v1/projects/${PROJECT_ID}/databases/(default)/documents`;
const UID = `memory-tx-user-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const ROOT = `users/${UID}`;
const CONTROL_PATH = `${ROOT}/memory_state/apply_control`;
const OPERATION_ID = 'operation-concurrent-apply';
const OPERATION_PATH = `${ROOT}/memory_operations/${OPERATION_ID}`;
const WINNER_COMMIT_ID = 'commit-from-attempt-a';
const LOSER_COMMIT_ID = 'commit-from-attempt-b';
const WINNER_MEMORY_ID = 'memory-from-attempt-a';
const LOSER_MEMORY_ID = 'memory-from-attempt-b';
const WINNER_OUTBOX_ID = 'outbox-from-attempt-a';
const LOSER_OUTBOX_ID = 'outbox-from-attempt-b';
const MAX_CONTENTION_ROUNDS = 3;

function documentName(path) {
  return `projects/${PROJECT_ID}/databases/(default)/documents/${path}`;
}

function valueToFirestore(value) {
  if (value === null || value === undefined) {
    return { nullValue: null };
  }
  if (typeof value === 'string') {
    return { stringValue: value };
  }
  if (typeof value === 'boolean') {
    return { booleanValue: value };
  }
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return { integerValue: String(value) };
    }
    return { doubleValue: value };
  }
  if (Array.isArray(value)) {
    return { arrayValue: { values: value.map(valueToFirestore) } };
  }
  return {
    mapValue: {
      fields: Object.fromEntries(Object.entries(value).map(([key, nested]) => [key, valueToFirestore(nested)])),
    },
  };
}

function firestoreToValue(value) {
  if (!value) return undefined;
  if ('nullValue' in value) return null;
  if ('stringValue' in value) return value.stringValue;
  if ('booleanValue' in value) return value.booleanValue;
  if ('integerValue' in value) return Number(value.integerValue);
  if ('doubleValue' in value) return value.doubleValue;
  if ('arrayValue' in value) return (value.arrayValue.values || []).map(firestoreToValue);
  if ('mapValue' in value) return fieldsToObject(value.mapValue.fields || {});
  return undefined;
}

function fieldsToObject(fields) {
  return Object.fromEntries(Object.entries(fields || {}).map(([key, nested]) => [key, firestoreToValue(nested)]));
}

function updateWrite(path, data) {
  return {
    update: {
      name: documentName(path),
      fields: Object.fromEntries(Object.entries(data).map(([key, value]) => [key, valueToFirestore(value)])),
    },
  };
}

function deleteWrite(path) {
  return { delete: documentName(path) };
}

async function firestoreRequest(endpoint, body, acceptedStatuses = [200]) {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { authorization: 'Bearer owner', 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data = {};
  if (text) {
    data = JSON.parse(text);
  }
  if (!acceptedStatuses.includes(response.status)) {
    throw new Error(`Firestore emulator request ${endpoint} failed with ${response.status}: ${text}`);
  }
  return { status: response.status, data };
}

async function commit(writes, transaction = undefined, acceptedStatuses = [200]) {
  return firestoreRequest(':commit', { writes, ...(transaction ? { transaction } : {}) }, acceptedStatuses);
}

async function beginTransaction() {
  const { data } = await firestoreRequest(':beginTransaction', { options: { readWrite: {} } });
  assert.ok(data.transaction, 'emulator returned a transaction id');
  return data.transaction;
}

async function batchGet(paths, transaction) {
  const { data } = await firestoreRequest(':batchGet', {
    documents: paths.map(documentName),
    transaction,
  });
  assert.ok(Array.isArray(data), 'batchGet returned a JSON stream array');
  return data;
}

async function getDocument(path) {
  const response = await fetch(`${BASE_URL}/${path}`, { headers: { authorization: 'Bearer owner' } });
  if (response.status === 404) return null;
  const text = await response.text();
  assert.equal(response.status, 200, `expected get ${path} to succeed: ${text}`);
  const document = JSON.parse(text);
  return fieldsToObject(document.fields || {});
}

async function seedInitialMemoryApplyState() {
  await commit([
    updateWrite(CONTROL_PATH, {
      uid: UID,
      head_commit_id: 'base-commit',
      commit_sequence: 0,
      account_generation: 11,
      source_generation: 22,
      updated_at: '2026-06-19T00:00:00Z',
    }),
    updateWrite(OPERATION_PATH, {
      uid: UID,
      operation_id: OPERATION_ID,
      status: 'pending',
      patch_hash: 'same-logical-patch',
      evidence_ids: ['evidence-a'],
      committed_sequence: null,
      committed_memory_item_ids: [],
      committed_outbox_event_ids: [],
    }),
  ]);
}

async function assertNoAttemptDocsWerePartiallyCommitted() {
  const control = await getDocument(CONTROL_PATH);
  const operation = await getDocument(OPERATION_PATH);
  assert.equal(control.head_commit_id, 'base-commit', 'double-aborted contention round left control head unchanged');
  assert.equal(control.commit_sequence, 0, 'double-aborted contention round left control sequence unchanged');
  assert.equal(operation.status, 'pending', 'double-aborted contention round left operation pending');
  assert.equal(operation.committed_sequence, null, 'double-aborted contention round did not store replay sequence');
  assert.deepEqual(
    operation.committed_memory_item_ids,
    [],
    'double-aborted contention round did not store replay memory IDs',
  );
  assert.deepEqual(
    operation.committed_outbox_event_ids,
    [],
    'double-aborted contention round did not store replay outbox IDs',
  );
  for (const path of [
    `${ROOT}/memory_commits/${WINNER_COMMIT_ID}`,
    `${ROOT}/memory_commits/${LOSER_COMMIT_ID}`,
    `${ROOT}/memory_items/${WINNER_MEMORY_ID}`,
    `${ROOT}/memory_items/${LOSER_MEMORY_ID}`,
    `${ROOT}/memory_outbox/${WINNER_OUTBOX_ID}`,
    `${ROOT}/memory_outbox/${LOSER_OUTBOX_ID}`,
  ]) {
    assert.equal(await getDocument(path), null, `double-aborted contention round did not write ${path}`);
  }
}

function attemptWrites({ commitId, memoryId, outboxId }) {
  return [
    updateWrite(OPERATION_PATH, {
      uid: UID,
      operation_id: OPERATION_ID,
      status: 'committed',
      patch_hash: 'same-logical-patch',
      evidence_ids: ['evidence-a'],
      committed_sequence: 1,
      committed_memory_item_ids: [memoryId],
      committed_outbox_event_ids: [outboxId],
    }),
    updateWrite(CONTROL_PATH, {
      uid: UID,
      head_commit_id: commitId,
      commit_sequence: 1,
      account_generation: 11,
      source_generation: 22,
      updated_at: '2026-06-19T00:00:01Z',
    }),
    updateWrite(`${ROOT}/memory_commits/${commitId}`, {
      uid: UID,
      commit_id: commitId,
      operation_id: OPERATION_ID,
      commit_sequence: 1,
      memory_item_ids: [memoryId],
      outbox_event_ids: [outboxId],
    }),
    updateWrite(`${ROOT}/memory_items/${memoryId}`, {
      uid: UID,
      memory_id: memoryId,
      status: 'active',
      memory_tier: 'long_term',
      account_generation: 11,
      source_generation: 22,
      content: 'transaction contention probe memory',
    }),
    updateWrite(`${ROOT}/memory_outbox/${outboxId}`, {
      uid: UID,
      event_id: outboxId,
      operation_id: OPERATION_ID,
      memory_id: memoryId,
      event_type: 'memory_item_upserted',
    }),
  ];
}

async function runContentionRound() {
  const attemptA = await beginTransaction();
  const attemptB = await beginTransaction();

  const [readA, readB] = await Promise.all([
    batchGet([CONTROL_PATH, OPERATION_PATH], attemptA),
    batchGet([CONTROL_PATH, OPERATION_PATH], attemptB),
  ]);
  assert.equal(readA.filter((entry) => entry.found).length, 2, 'attempt A read control + operation');
  assert.equal(readB.filter((entry) => entry.found).length, 2, 'attempt B read control + operation');

  const [commitA, commitB] = await Promise.all([
    commit(
      attemptWrites({ commitId: WINNER_COMMIT_ID, memoryId: WINNER_MEMORY_ID, outboxId: WINNER_OUTBOX_ID }),
      attemptA,
      [200, 409],
    ),
    commit(
      attemptWrites({ commitId: LOSER_COMMIT_ID, memoryId: LOSER_MEMORY_ID, outboxId: LOSER_OUTBOX_ID }),
      attemptB,
      [200, 409],
    ),
  ]);
  return { commitA, commitB };
}

async function assertConcurrentTransactionContentionSerializesMemoryApply() {
  await seedInitialMemoryApplyState();

  let commitA;
  let commitB;
  for (let round = 1; round <= MAX_CONTENTION_ROUNDS; round += 1) {
    ({ commitA, commitB } = await runContentionRound());
    const statuses = [commitA.status, commitB.status].sort();
    if (statuses[0] === 200 && statuses[1] === 409) {
      break;
    }
    assert.deepEqual(
      statuses,
      [409, 409],
      `unexpected contention result in round ${round}; expected one commit or clean double-abort`,
    );
    assert.notEqual(round, MAX_CONTENTION_ROUNDS, 'contention never produced a serialized commit before retry limit');
    await assertNoAttemptDocsWerePartiallyCommitted();
  }

  assert.ok(commitA && commitB, 'contention produced commit responses');
  const statuses = [commitA.status, commitB.status].sort();
  assert.deepEqual(statuses, [200, 409], 'exactly one concurrent apply transaction commits after bounded retry');

  const winningIds =
    commitA.status === 200
      ? { commitId: WINNER_COMMIT_ID, memoryId: WINNER_MEMORY_ID, outboxId: WINNER_OUTBOX_ID }
      : { commitId: LOSER_COMMIT_ID, memoryId: LOSER_MEMORY_ID, outboxId: LOSER_OUTBOX_ID };
  const losingIds =
    commitA.status === 200
      ? { commitId: LOSER_COMMIT_ID, memoryId: LOSER_MEMORY_ID, outboxId: LOSER_OUTBOX_ID }
      : { commitId: WINNER_COMMIT_ID, memoryId: WINNER_MEMORY_ID, outboxId: WINNER_OUTBOX_ID };

  const retry = await beginTransaction();
  const retryRead = await batchGet([CONTROL_PATH, OPERATION_PATH], retry);
  const retryDocs = Object.fromEntries(
    retryRead.filter((entry) => entry.found).map((entry) => [entry.found.name, fieldsToObject(entry.found.fields)]),
  );
  assert.equal(retryDocs[documentName(CONTROL_PATH)].head_commit_id, winningIds.commitId);
  assert.equal(retryDocs[documentName(OPERATION_PATH)].status, 'committed');
  assert.deepEqual(retryDocs[documentName(OPERATION_PATH)].committed_memory_item_ids, [winningIds.memoryId]);
  await commit([], retry);

  assert.equal((await getDocument(CONTROL_PATH)).head_commit_id, winningIds.commitId);
  assert.equal((await getDocument(OPERATION_PATH)).committed_sequence, 1);
  assert.ok(await getDocument(`${ROOT}/memory_commits/${winningIds.commitId}`));
  assert.ok(await getDocument(`${ROOT}/memory_items/${winningIds.memoryId}`));
  assert.ok(await getDocument(`${ROOT}/memory_outbox/${winningIds.outboxId}`));
  assert.equal(await getDocument(`${ROOT}/memory_commits/${losingIds.commitId}`), null);
  assert.equal(await getDocument(`${ROOT}/memory_items/${losingIds.memoryId}`), null);
  assert.equal(await getDocument(`${ROOT}/memory_outbox/${losingIds.outboxId}`), null);
}

try {
  await assertConcurrentTransactionContentionSerializesMemoryApply();
  console.log('PASS: Firestore emulator transaction contention serialized memory apply layout');
} finally {
  await commit([
    deleteWrite(`${ROOT}/memory_outbox/${WINNER_OUTBOX_ID}`),
    deleteWrite(`${ROOT}/memory_outbox/${LOSER_OUTBOX_ID}`),
    deleteWrite(`${ROOT}/memory_items/${WINNER_MEMORY_ID}`),
    deleteWrite(`${ROOT}/memory_items/${LOSER_MEMORY_ID}`),
    deleteWrite(`${ROOT}/memory_commits/${WINNER_COMMIT_ID}`),
    deleteWrite(`${ROOT}/memory_commits/${LOSER_COMMIT_ID}`),
    deleteWrite(OPERATION_PATH),
    deleteWrite(CONTROL_PATH),
  ], undefined, [200, 404]).catch(() => undefined);
}
