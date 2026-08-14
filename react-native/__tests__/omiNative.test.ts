import {
  resolveOmiBackend,
  resolveOmiNative,
  type NativeHttpRequest,
  type NativeHttpResponse,
  type OmiBackend,
  type OmiNative,
} from '../src/omiNative';

test('native module selection keeps a registered implementation', () => {
  const nativeModule = {} as OmiNative;

  const selected = resolveOmiNative(nativeModule);

  expect(selected.installed).toBe(true);
  expect(selected.adapter).toBe(nativeModule);
});

test('native module selection reports an unavailable platform without a simulator', () => {
  const selected = resolveOmiNative(undefined);

  expect(selected.installed).toBe(false);
  expect(selected.adapter).toBeUndefined();
});

test('native HTTP contract exposes only an origin-relative request and normalized response', async () => {
  const captured: NativeHttpRequest[] = [];
  const nativeModule: OmiBackend = {
    request: async (
      request: NativeHttpRequest,
    ): Promise<NativeHttpResponse> => {
      captured.push(request);
      return {id: request.id, status: 200, body: '{"status":"ok"}'};
    },
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
  const request: NativeHttpRequest = {
    id: 'request-1',
    method: 'POST',
    path: '/v1/chat-messages',
    headers: {'x-request-label': 'chat'},
    body: '{"text":"hello"}',
  };

  const selected = resolveOmiBackend(nativeModule);
  const response = await selected.adapter!.request(request);

  expect(captured).toEqual([request]);
  expect(Object.keys(captured[0]).sort()).toEqual([
    'body',
    'headers',
    'id',
    'method',
    'path',
  ]);
  expect(response).toEqual({
    id: 'request-1',
    status: 200,
    body: '{"status":"ok"}',
  });
  expect(selected.installed).toBe(true);
});
