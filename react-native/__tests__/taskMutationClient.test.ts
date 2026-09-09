import {prepareTaskPatch, sendTaskPatch} from '../src/taskMutationClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNativeTypes';

const writeId = 'a'.repeat(64);
const revision = 'b'.repeat(64);
const nextRevision = 'c'.repeat(64);
function client() {
  return {
    createWriteId: jest.fn(async () => writeId),
    request: jest.fn(async (_request: NativeHttpRequest) => ({
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

function omiClient() {
  return {
    ...client(),
    getApiContract: jest.fn(async (): Promise<'omi' | 'canonical'> => 'omi'),
  };
}
const omiInput = {
  apiContract: 'omi' as const,
  recordId: 'old task',
  baseRevision: null,
  accountEpoch: null,
  patch: {completed: true, description: 'Call Sam'},
};
function omiResponse(
  completed = true,
  description = 'Call Sam',
  id = 'old task',
) {
  return {
    id: 'response',
    status: 200,
    body: JSON.stringify({
      id,
      completed,
      description,
      completed_at: '2026-09-07T00:00:00Z',
    }),
  };
}

test('old task patch sends only supported fields and validates bare action item acknowledgement', async () => {
  const backend = omiClient();
  backend.request.mockResolvedValue(omiResponse());
  const prepared = await prepareTaskPatch(backend, omiInput);
  expect(backend.createWriteId).not.toHaveBeenCalled();
  expect(prepared.body).toBe(JSON.stringify(omiInput.patch));
  expect(await sendTaskPatch(backend, prepared)).toEqual({
    ok: true,
    revision: null,
  });
  expect(backend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'PATCH',
    expectedApiContract: 'omi',
    path: '/v1/action-items/old%20task',
    body: prepared.body,
  });
});

test.each([true, false])(
  'uncertain old PATCH reconciles GET only and never overwrites concurrent state (matches=%s)',
  async matches => {
    const backend = omiClient();
    backend.request
      .mockRejectedValueOnce(new TypeError('Lost acknowledgement'))
      .mockResolvedValue(omiResponse(matches));
    const prepared = await prepareTaskPatch(backend, omiInput);
    expect((await sendTaskPatch(backend, prepared)).ok).toBe(false);
    const result = await sendTaskPatch(backend, prepared);
    expect(result).toMatchObject(
      matches
        ? {ok: true, revision: null}
        : {ok: false, failure: {kind: 'permanent', reason: 'conflict'}},
    );
    await sendTaskPatch(backend, prepared);
    expect(
      backend.request.mock.calls.map(
        call => (call[0] as unknown as {method: string}).method,
      ),
    ).toEqual(['PATCH', 'GET', 'GET']);
    expect(backend.request.mock.calls[1]?.[0]).toEqual({
      id: expect.any(String),
      method: 'GET',
      expectedApiContract: 'omi',
      path: '/v1/action-items/old%20task',
    });
  },
);

test('wrong old task acknowledgement remains uncertain and changed backend refuses any subsequent request', async () => {
  const backend = omiClient();
  backend.request.mockResolvedValue(
    omiResponse(true, 'Call Sam', 'another-task'),
  );
  const prepared = await prepareTaskPatch(backend, omiInput);
  expect((await sendTaskPatch(backend, prepared)).ok).toBe(false);
  backend.getApiContract.mockResolvedValue('canonical');
  expect(await sendTaskPatch(backend, prepared)).toMatchObject({
    ok: false,
    failure: {kind: 'permanent'},
  });
  expect(backend.request).toHaveBeenCalledTimes(1);
});

test('native plane-switch rejection is permanent for both contracts', async () => {
  for (const old of [false, true]) {
    const backend = omiClient();
    backend.request.mockRejectedValue({code: 'OMI_HTTP_BACKEND_CHANGED'});
    const prepared = await prepareTaskPatch(backend, old ? omiInput : input);
    expect(await sendTaskPatch(backend, prepared)).toMatchObject({
      ok: false,
      failure: {kind: 'permanent'},
    });
  }
});

test('nested non-retryable task write 503s are permanent without control-unavailable retry', async () => {
  const backend = client();
  const prepared = await prepareTaskPatch(backend, input);
  backend.request.mockResolvedValue({
    id: 'request',
    status: 503,
    body: '{"error":{"code":"development_backend_unsupported","retryable":false,"action":"none"}}',
  });
  expect(await sendTaskPatch(backend, prepared)).toMatchObject({
    ok: false,
    failure: {kind: 'permanent'},
    controlUnavailable: false,
  });
});

test('native unsupported task-write rejection is permanent for both contracts', async () => {
  for (const old of [false, true]) {
    const backend = omiClient();
    backend.request.mockRejectedValue({code: 'OMI_DEV_BACKEND_UNSUPPORTED'});
    const prepared = await prepareTaskPatch(backend, old ? omiInput : input);
    expect(await sendTaskPatch(backend, prepared)).toMatchObject({
      ok: false,
      failure: {kind: 'permanent'},
      controlUnavailable: false,
    });
  }
});

test('thrown nested non-retryable task writes are permanent', async () => {
  const backend = client();
  const prepared = await prepareTaskPatch(backend, input);
  backend.request.mockRejectedValue(
    Object.assign(new Error('unsupported'), {retryable: false}),
  );
  expect(await sendTaskPatch(backend, prepared)).toMatchObject({
    ok: false,
    failure: {kind: 'permanent'},
    controlUnavailable: false,
  });
});

test('old task rate limit retains Retry-After and subsequent check is read-only', async () => {
  const backend = omiClient();
  backend.request
    .mockResolvedValueOnce({
      ...omiResponse(),
      status: 429,
      retryAfterSeconds: 12,
    } as ReturnType<typeof omiResponse>)
    .mockResolvedValue(omiResponse());
  const prepared = await prepareTaskPatch(backend, omiInput);
  expect(await sendTaskPatch(backend, prepared)).toMatchObject({
    ok: false,
    failure: {kind: 'rate-limited', retryAfterMs: 12000},
  });
  expect((await sendTaskPatch(backend, prepared)).ok).toBe(true);
  expect(backend.request.mock.calls.map(([request]) => request.method)).toEqual(
    ['PATCH', 'GET'],
  );
});
