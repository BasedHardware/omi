import type {NativeHttpRequest, OmiBackend} from '../src/omiNativeTypes';
import {
  conversationShareUrl,
  createMemory,
  deleteMemory,
  editMemory,
  setMemoryVisibility,
  deleteConversation,
  listFolders,
  moveConversationToFolder,
  reprocessConversation,
  setConversationStarred,
  setConversationTitle,
  setConversationVisibility,
} from '../src/legacyOmiWrites';

function backend(status = 200, body: string | null = '{"status":"Ok"}') {
  const requests: NativeHttpRequest[] = [];
  const value = {
    getApiContract: jest.fn(async () => 'omi' as const),
    request: jest.fn(async (request: NativeHttpRequest) => {
      requests.push(request);
      return {id: request.id, status, body};
    }),
  } as unknown as OmiBackend;
  return {value, requests};
}

test('delete sends cascade true and treats 503 as retryable', async () => {
  const {value, requests} = backend();
  expect(await deleteConversation(value, 'a/b')).toEqual({
    ok: true,
    value: {status: 'Ok'},
  });
  expect(requests[0]).toMatchObject({
    method: 'DELETE',
    path: '/v1/conversations/a%2Fb?cascade=true',
    expectedApiContract: 'omi',
  });
  const busy = backend(503);
  const result = await deleteConversation(busy.value, 'id');
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.failure.kind).toBe('retryable');
});

test('title is an encoded query parameter with no body', async () => {
  const {value, requests} = backend();
  await setConversationTitle(value, 'id', 'plan & ship/✓');
  expect(requests[0]).toMatchObject({
    method: 'PATCH',
    path: '/v1/conversations/id/title?title=plan%20%26%20ship%2F%E2%9C%93',
  });
  expect(requests[0].body).toBeUndefined();
});

test('reprocess uses only query parameters, no body, and a 180 second timeout', async () => {
  const {value, requests} = backend();
  await reprocessConversation(value, 'id', {
    languageCode: 'en-US',
    appId: 'app/1',
  });
  expect(requests[0]).toMatchObject({
    method: 'POST',
    path: '/v1/conversations/id/reprocess?language_code=en-US&app_id=app%2F1',
    timeoutSeconds: 180,
  });
  expect(requests[0].body).toBeUndefined();
});

test('visibility uses a query parameter and no body', async () => {
  const {value, requests} = backend();
  await setConversationVisibility(value, 'id', 'shared');
  expect(requests[0]).toMatchObject({
    method: 'PATCH',
    path: '/v1/conversations/id/visibility?value=shared',
  });
  expect(requests[0].body).toBeUndefined();
});

test('starred state uses a query parameter and no body', async () => {
  const {value, requests} = backend();
  await setConversationStarred(value, 'id', true);
  expect(requests[0]).toMatchObject({
    method: 'PATCH',
    path: '/v1/conversations/id/starred?starred=true',
  });
  expect(requests[0].body).toBeUndefined();
});

test('folder list and folder move use the legacy route and body contracts', async () => {
  const {value, requests} = backend(200, '[{"id":"work","name":"Work"}]');
  expect(await listFolders(value)).toEqual({
    ok: true,
    value: [{id: 'work', name: 'Work'}],
  });
  await moveConversationToFolder(value, 'id', null);
  expect(
    requests.map(({method, path, body}) => ({method, path, body})),
  ).toEqual([
    {method: 'GET', path: '/v1/folders', body: undefined},
    {
      method: 'PATCH',
      path: '/v1/conversations/id/folder',
      body: '{"folder_id":null}',
    },
  ]);
});

test('malformed folder list is retryable unknown', async () => {
  const {value} = backend(200, '{"folders":[]}');
  const result = await listFolders(value);
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.failure.kind).toBe('retryable');
});

test.each([
  [401, 'auth-invalid'],
  [429, 'rate-limited'],
  [400, 'permanent'],
  [403, 'permanent'],
  [404, 'permanent'],
  [409, 'permanent'],
  [422, 'permanent'],
  [500, 'retryable'],
  [503, 'retryable'],
])('maps status %i to %s', async (status, kind) => {
  const {value} = backend(status);
  const result = await setConversationStarred(value, 'id', false);
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.failure.kind).toBe(kind);
});

test('the Omi contract gate rejects before a write', async () => {
  const {value, requests} = backend();
  (value.getApiContract as jest.Mock).mockResolvedValue('canonical');
  const result = await deleteConversation(value, 'id');
  expect(result.ok).toBe(false);
  expect(requests).toHaveLength(0);
});

test('share URL contains the mac source and a random 32 digit hex sid', () => {
  const first = conversationShareUrl('abc');
  const second = conversationShareUrl('abc');
  expect(first).toMatch(
    /^https:\/\/h\.omi\.me\/conversations\/abc\?s=mac&sid=[0-9a-f]{32}$/,
  );
  expect(second).not.toBe(first);
});

describe('legacy memory writes', () => {
  const memoryResponse = (status: number, body: unknown = {status: 'ok'}) => ({
    id: 'request',
    status,
    body: body === null ? null : JSON.stringify(body),
  });
  const memoryBackend = (
    status: number,
    body: unknown = {status: 'ok'},
  ): OmiBackend => ({
    getApiContract: jest.fn(async () => 'omi' as const),
    request: jest.fn(async () => memoryResponse(status, body)),
    generationEvents: jest.fn(),
    cancelGenerationEvents: jest.fn(),
  });

  test('create sends the manual private memory body and returns the created row', async () => {
    const record = {id: 'memory-1', content: 'A fact'};
    const api = memoryBackend(200, record);
    await expect(createMemory(api, 'A fact')).resolves.toEqual({
      ok: true,
      value: record,
    });
    expect(api.request).toHaveBeenCalledWith({
      id: 'omi-memory-post',
      method: 'POST',
      expectedApiContract: 'omi',
      path: '/v3/memories',
      body: JSON.stringify({
        content: 'A fact',
        category: 'manual',
        visibility: 'private',
        tags: [],
      }),
    });
  });

  test('edit sends exactly the value field', async () => {
    const api = memoryBackend(200);
    await expect(editMemory(api, 'memory/1', 'Updated')).resolves.toMatchObject(
      {
        ok: true,
      },
    );
    expect(api.request).toHaveBeenCalledWith({
      id: 'omi-memory-patch',
      method: 'PATCH',
      expectedApiContract: 'omi',
      path: '/v3/memories/memory%2F1',
      body: '{"value":"Updated"}',
    });
  });

  test('visibility sends exactly the value field', async () => {
    const api = memoryBackend(200);
    await expect(
      setMemoryVisibility(api, 'memory-1', 'public'),
    ).resolves.toMatchObject({ok: true});
    expect(api.request).toHaveBeenCalledWith({
      id: 'omi-memory-patch',
      method: 'PATCH',
      expectedApiContract: 'omi',
      path: '/v3/memories/memory-1/visibility',
      body: '{"value":"public"}',
    });
  });

  test('delete treats 404 as success', async () => {
    const api = memoryBackend(404);
    await expect(deleteMemory(api, 'memory-1')).resolves.toEqual({
      ok: true,
      value: undefined,
    });
    expect(api.request).toHaveBeenCalledWith({
      id: 'omi-memory-delete',
      method: 'DELETE',
      expectedApiContract: 'omi',
      path: '/v3/memories/memory-1',
    });
  });

  test('memory writes map auth, rate-limit, permanent, and unconfirmed responses', async () => {
    await expect(createMemory(memoryBackend(401), 'A')).resolves.toMatchObject({
      ok: false,
      failure: {kind: 'auth-invalid'},
    });
    await expect(createMemory(memoryBackend(429), 'A')).resolves.toMatchObject({
      ok: false,
      failure: {kind: 'rate-limited'},
    });
    await expect(createMemory(memoryBackend(422), 'A')).resolves.toMatchObject({
      ok: false,
      failure: {kind: 'permanent', reason: 'validation'},
    });
    await expect(createMemory(memoryBackend(503), 'A')).resolves.toMatchObject({
      ok: false,
      failure: {kind: 'retryable'},
    });
  });
});
