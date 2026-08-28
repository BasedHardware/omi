import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  DeviceSessionBackendError,
  openDeviceSession,
} from '../src/deviceSessionClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: '11111111-2222-3333-4444-555555555555',
    deviceId: 'omi-1',
    deviceName: 'Omi',
    codec: 21,
    state: 'open',
    byteCount: 0,
    chunkCount: 0,
    startedAt: 1,
    endedAt: null,
    ...overrides,
  };
}

function backend(
  handler: (request: NativeHttpRequest) => {
    status: number;
    body: string | null;
  },
): OmiBackend {
  return {
    request: async (request: NativeHttpRequest) => ({
      id: request.id,
      status: handler(request).status,
      body: handler(request).body,
    }),
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
}

test('opens a device session on the worker path and refuses invented transcripts', async () => {
  const captured: NativeHttpRequest[] = [];
  const client = backend(request => {
    captured.push(request);
    return {
      status: 201,
      body: JSON.stringify({session: session()}),
    };
  });

  const opened = await openDeviceSession(client, {
    deviceId: 'omi-1',
    deviceName: 'Omi',
    codec: 21,
  });

  expect(captured[0]?.path).toBe('/v1/device-sessions');
  expect(captured[0]?.path).not.toContain('api.omi.me');
  expect(opened.id).toBe('11111111-2222-3333-4444-555555555555');
  await expect(
    openDeviceSession(
      backend(() => ({
        status: 201,
        body: JSON.stringify({
          session: {...session(), transcript: 'hello'},
        }),
      })),
      {deviceId: 'omi-1', codec: 21},
    ),
  ).rejects.toThrow('invented a transcript');
});

test('appends audio bytes and completes without a fake transcript', async () => {
  const captured: NativeHttpRequest[] = [];
  const client = backend(request => {
    captured.push(request);
    if (request.path.endsWith('/audio')) {
      return {
        status: 200,
        body: JSON.stringify({session: session({byteCount: 3, chunkCount: 1})}),
      };
    }
    return {
      status: 200,
      body: JSON.stringify({
        session: session({state: 'complete', byteCount: 3, endedAt: 2}),
      }),
    };
  });

  const appended = await appendDeviceSessionAudio(
    client,
    '11111111-2222-3333-4444-555555555555',
    new Uint8Array([1, 2, 3]),
  );
  const completed = await completeDeviceSession(
    client,
    '11111111-2222-3333-4444-555555555555',
  );

  expect(captured[0]?.path).toBe(
    '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
  );
  expect(JSON.parse(captured[0]?.body ?? '{}')).toEqual({
    bytesBase64: 'AQID',
  });
  expect(appended.byteCount).toBe(3);
  expect(completed.state).toBe('complete');
  expect(completed).not.toHaveProperty('transcript');
});

test('fail-closes when the worker is unavailable', async () => {
  await expect(
    openDeviceSession(
      backend(() => ({
        status: 503,
        body: JSON.stringify({
          error: {
            code: 'service_unavailable',
            retryable: true,
            action: 'retry',
          },
        }),
      })),
      {deviceId: 'omi-1', codec: 21},
    ),
  ).rejects.toBeInstanceOf(DeviceSessionBackendError);
});
