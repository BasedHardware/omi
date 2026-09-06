import {prepareTaskPatch, sendTaskPatch} from '../src/taskMutationClient';
import type {OmiBackend} from '../src/omiNativeTypes';

const writeId = 'a'.repeat(64);
const revision = 'b'.repeat(64);
const nextRevision = 'c'.repeat(64);
function client() {
  return {
    createWriteId: jest.fn(async () => writeId),
    request: jest.fn(async () => ({
      id: 'request',
      status: 200,
      body: JSON.stringify({
        applied: {record_id: 'storage-id', revision: nextRevision},
        idempotent: false,
      }),
    })),
    generationEvents: jest.fn(),
    cancelGenerationEvents: jest.fn(),
  } satisfies OmiBackend;
}
const input = {
  recordId: 'task:reader-id',
  baseRevision: revision,
  accountEpoch: 0,
  patch: {completed: true},
};

test('prepares one keyed patch with revision and entropy identity, replays exact body after response loss', async () => {
  const backend = client();
  backend.request.mockRejectedValueOnce(new TypeError('response lost'));
  const prepared = await prepareTaskPatch(backend, input);
  const envelope = JSON.parse(prepared.body);
  expect(envelope).toMatchObject({
    write_id: writeId,
    account_epoch: 0,
    domain: 'tasks',
    op: {
      op: 'patch',
      record_id: input.recordId,
      base_revision: revision,
      patch: {completed: true},
    },
  });
  expect(envelope.op.patch.completedAt).toBe(envelope.op.patch.updatedAt);
  expect(envelope.op.patch.updatedAt).toBeGreaterThan(1_000_000_000_000);
  expect(Object.keys(envelope.op.patch).sort()).toEqual([
    'completed',
    'completedAt',
    'updatedAt',
  ]);
  expect((await sendTaskPatch(backend, prepared)).ok).toBe(false);
  expect(await sendTaskPatch(backend, prepared)).toEqual({
    ok: true,
    revision: nextRevision,
  });
  expect(backend.createWriteId).toHaveBeenCalledTimes(1);
  expect(backend.request.mock.calls[0]).toEqual(backend.request.mock.calls[1]);
});

test('reopening clears completion time and description edits preserve unrelated fields', async () => {
  const backend = client();
  const reopened = JSON.parse(
    (await prepareTaskPatch(backend, {...input, patch: {completed: false}}))
      .body,
  );
  expect(reopened.op.patch).toMatchObject({
    completed: false,
    completedAt: null,
  });
  const edited = JSON.parse(
    (
      await prepareTaskPatch(backend, {
        ...input,
        patch: {description: 'Edited'},
      })
    ).body,
  );
  expect(Object.keys(edited.op.patch).sort()).toEqual([
    'description',
    'updatedAt',
  ]);
});

test.each([null, -1, 1.5])(
  'refuses invalid account epoch %s',
  async accountEpoch => {
    const backend = client();
    await expect(
      prepareTaskPatch(backend, {
        ...input,
        accountEpoch: accountEpoch as number,
      }),
    ).rejects.toThrow();
    expect(backend.request).not.toHaveBeenCalled();
  },
);

test('refuses UUID-derived or missing write identity capability', async () => {
  const backend = client();
  backend.createWriteId.mockResolvedValue(
    '11111111-2222-4333-8444-555555555555',
  );
  await expect(prepareTaskPatch(backend, input)).rejects.toThrow();
  await expect(
    prepareTaskPatch({...backend, createWriteId: undefined}, input),
  ).rejects.toThrow();
});

test.each([
  [
    409,
    '{"error":"stale_epoch","refusal_outcome":"stale_epoch"}',
    'permanent',
    'stale_epoch',
  ],
  [409, '{"error":"conflict"}', 'permanent', 'conflict'],
  [
    503,
    '{"error":"maintenance","refusal_outcome":"control_unavailable"}',
    'retryable',
    undefined,
  ],
  [
    401,
    '{"error":"unauthorized","refusal_outcome":"authentication"}',
    'auth-invalid',
    undefined,
  ],
])(
  'classifies response %s %s without claiming success',
  async (status, body, kind, reason) => {
    const backend = client();
    const prepared = await prepareTaskPatch(backend, input);
    backend.request.mockResolvedValue({
      id: 'request',
      status: status as number,
      body: body as string,
    });
    const result = await sendTaskPatch(backend, prepared);
    expect(result).toMatchObject({
      ok: false,
      failure: {kind, ...(reason ? {reason} : {})},
      controlUnavailable:
        body ===
        '{"error":"maintenance","refusal_outcome":"control_unavailable"}',
    });
  },
);

test('retains ambiguous malformed success for explicit retry', async () => {
  const backend = client();
  const prepared = await prepareTaskPatch(backend, input);
  backend.request.mockResolvedValue({id: 'request', status: 200, body: '{}'});
  expect(await sendTaskPatch(backend, prepared)).toMatchObject({
    ok: false,
    failure: {kind: 'retryable'},
  });
});
