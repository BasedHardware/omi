import type {OmiBackend} from '../src/omiNative';
import {
  createMemory,
  deleteMemory,
  editMemory,
  setMemoryVisibility,
} from '../src/legacyOmiWrites';

const response = (status: number, body: unknown = {status: 'ok'}) => ({
  id: 'request',
  status,
  body: body === null ? null : JSON.stringify(body),
});
const backend = (
  status: number,
  body: unknown = {status: 'ok'},
): OmiBackend => ({
  getApiContract: jest.fn(async () => 'omi' as const),
  request: jest.fn(async () => response(status, body)),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(),
});

test('create sends the manual private memory body and returns the created row', async () => {
  const record = {id: 'memory-1', content: 'A fact'};
  const api = backend(200, record);
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
  const api = backend(200);
  await expect(editMemory(api, 'memory/1', 'Updated')).resolves.toMatchObject({
    ok: true,
  });
  expect(api.request).toHaveBeenCalledWith({
    id: 'omi-memory-patch',
    method: 'PATCH',
    expectedApiContract: 'omi',
    path: '/v3/memories/memory%2F1',
    body: '{"value":"Updated"}',
  });
});

test('visibility sends exactly the value field', async () => {
  const api = backend(200);
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
  const api = backend(404);
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

test('memory writes map auth, rate-limit, permanent, and unknown responses', async () => {
  await expect(createMemory(backend(401), 'A')).resolves.toMatchObject({
    ok: false,
    failure: {kind: 'auth-invalid'},
  });
  await expect(createMemory(backend(429), 'A')).resolves.toMatchObject({
    ok: false,
    failure: {kind: 'rate-limited'},
  });
  await expect(createMemory(backend(422), 'A')).resolves.toMatchObject({
    ok: false,
    failure: {kind: 'permanent', status: 422},
  });
  await expect(createMemory(backend(503), 'A')).resolves.toMatchObject({
    ok: false,
    failure: {kind: 'unknown'},
  });
});
