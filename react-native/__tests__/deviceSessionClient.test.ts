import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  DeviceSessionBackendError,
  openDeviceSession,
  transcribeDeviceSession,
  isTransientDeviceSessionError,
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
    createRecordingId: async () => '11111111-2222-4333-8444-555555555555',
    request: async (request: NativeHttpRequest) => ({
      id: request.id,
      status: handler(request).status,
      body: handler(request).body,
    }),
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
}

test('resumes transcription through bodyless native transport and validates account-scoped reply', async () => {
  const requests: NativeHttpRequest[] = [];
  const transcription = {
    sessionId: 'recording-one',
    state: 'running',
    text: null,
    segments: [],
    language: null,
    errorCode: null,
    updatedAt: 1,
    discardedLeadingPackets: 0,
  };
  const client = backend(request => {
    requests.push(request);
    return {status: 202, body: JSON.stringify({transcription})};
  });
  await expect(
    transcribeDeviceSession(client, 'recording-one'),
  ).resolves.toEqual({
    sessionId: 'recording-one',
    state: 'running',
    text: null,
    errorCode: null,
    discardedLeadingPackets: 0,
  });
  expect(requests[0]).toEqual({
    id: 'device-session-transcribe-recording-one',
    method: 'POST',
    path: '/v1/device-sessions/recording-one/transcribe',
  });
  await expect(
    transcribeDeviceSession(client, 'other-recording'),
  ).rejects.toThrow('did not acknowledge');
  await expect(
    transcribeDeviceSession(
      backend(() => ({status: 503, body: null})),
      'recording-one',
    ),
  ).rejects.toBeInstanceOf(DeviceSessionBackendError);
});

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
    captureId: '11111111-2222-4333-8444-555555555555',
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
      {
        captureId: '11111111-2222-4333-8444-555555555555',
        deviceId: 'omi-1',
        codec: 21,
      },
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
    [new Uint8Array([1, 2, 3])],
    0,
  );
  const completed = await completeDeviceSession(
    client,
    '11111111-2222-3333-4444-555555555555',
  );

  expect(captured[0]?.path).toBe(
    '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
  );
  expect(JSON.parse(captured[0]?.body ?? '{}')).toEqual({
    chunks: [{bytesBase64: 'AQID', chunkIndex: 0}],
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
      {
        captureId: '11111111-2222-4333-8444-555555555555',
        deviceId: 'omi-1',
        codec: 21,
      },
    ),
  ).rejects.toBeInstanceOf(DeviceSessionBackendError);
});

test('does not treat nested non-retryable capture 503s as transient', async () => {
  await expect(
    openDeviceSession(
      backend(() => ({
        status: 503,
        body: JSON.stringify({
          error: {
            code: 'development_backend_unsupported',
            retryable: false,
            action: 'none',
          },
        }),
      })),
      {
        captureId: '11111111-2222-4333-8444-555555555555',
        deviceId: 'omi-1',
        codec: 21,
      },
    ),
  ).rejects.toMatchObject({
    status: 503,
    backendCode: 'development_backend_unsupported',
    retryable: false,
  });
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(
        503,
        'development_backend_unsupported',
        false,
      ),
    ),
  ).toBe(false);
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(503, 'capture_ownership_unavailable', true),
    ),
  ).toBe(false);
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(
        503,
        'capture_ownership_unavailable',
        false,
      ),
    ),
  ).toBe(false);
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(503, 'service_unavailable', true),
    ),
  ).toBe(true);
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(503, 'unknown'),
    ),
  ).toBe(true);
  expect(
    isTransientDeviceSessionError(
      new DeviceSessionBackendError(500, 'unknown'),
    ),
  ).toBe(true);
});

test.each([
  {id: 'another-session', byteCount: 3, chunkCount: 1},
  {byteCount: 3, chunkCount: 0},
  {byteCount: 2, chunkCount: 1},
  {byteCount: Number.NaN, chunkCount: 1},
  {byteCount: 3, chunkCount: 1, state: 'failed'},
])('refuses an invalid acknowledgement %j', async overrides => {
  await expect(
    appendDeviceSessionAudio(
      backend(() => ({
        status: 200,
        body: JSON.stringify({session: session(overrides)}),
      })),
      '11111111-2222-3333-4444-555555555555',
      [new Uint8Array([1, 2, 3])],
      0,
    ),
  ).rejects.toThrow();
});

test.each([{id: 'another-session', state: 'complete'}, {state: 'open'}])(
  'refuses an invalid completion acknowledgement %j',
  async overrides => {
    await expect(
      completeDeviceSession(
        backend(() => ({
          status: 200,
          body: JSON.stringify({session: session(overrides)}),
        })),
        '11111111-2222-3333-4444-555555555555',
      ),
    ).rejects.toThrow();
  },
);

test.each([
  {deviceId: 'other'},
  {deviceName: 'other'},
  {codec: 20},
  {state: 'failed'},
])(
  'rejects an open acknowledgement for different capture metadata %j',
  async overrides => {
    await expect(
      openDeviceSession(
        backend(() => ({
          status: 200,
          body: JSON.stringify({session: session(overrides)}),
        })),
        {
          captureId: '11111111-2222-4333-8444-555555555555',
          deviceId: 'omi-1',
          deviceName: 'Omi',
          codec: 21,
        },
      ),
    ).rejects.toThrow('recording identity');
  },
);

test.each(['not-a-uuid', 'AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE'])(
  'rejects invalid recording identity %s before HTTP dispatch',
  async captureId => {
    const handler = jest.fn(() => ({
      status: 201,
      body: JSON.stringify({session: session()}),
    }));
    await expect(
      openDeviceSession(backend(handler), {
        captureId,
        deviceId: 'omi-1',
        codec: 21,
      }),
    ).rejects.toThrow('Invalid recording identity');
    expect(handler).not.toHaveBeenCalled();
  },
);

test('batches preserve every BLE packet and require acknowledgement through the final index', async () => {
  const captured: NativeHttpRequest[] = [];
  const client = backend(request => {
    captured.push(request);
    return {
      status: 200,
      body: JSON.stringify({session: session({chunkCount: 4, byteCount: 6})}),
    };
  });
  await appendDeviceSessionAudio(
    client,
    '11111111-2222-3333-4444-555555555555',
    [new Uint8Array([1, 2, 3]), new Uint8Array([4, 5, 6])],
    2,
  );
  expect(JSON.parse(captured[0]!.body!)).toEqual({
    chunks: [
      {chunkIndex: 2, bytesBase64: 'AQID'},
      {chunkIndex: 3, bytesBase64: 'BAUG'},
    ],
  });
  await expect(
    appendDeviceSessionAudio(
      backend(() => ({
        status: 200,
        body: JSON.stringify({session: session({chunkCount: 3, byteCount: 6})}),
      })),
      '11111111-2222-3333-4444-555555555555',
      [new Uint8Array([1, 2, 3]), new Uint8Array([4, 5, 6])],
      2,
    ),
  ).rejects.toThrow('audio batch');
});

test('rejects over-budget batches before transport', async () => {
  const send = jest.fn(() => ({status: 200, body: '{}'}));
  const client = backend(send);
  for (const [packets, index] of [
    [[], 0],
    [[new Uint8Array(0)], 0],
    [Array.from({length: 129}, () => new Uint8Array([1])), 0],
    [[new Uint8Array(1048577)], 0],
    [[new Uint8Array([1]), new Uint8Array([2])], 65535],
  ] as const)
    await expect(
      appendDeviceSessionAudio(client, 'session', packets, index),
    ).rejects.toThrow();
  expect(send).not.toHaveBeenCalled();
});

test('open preserves optional device capture time and rejects changed acknowledgements', async () => {
  const input = {
    captureId: '11111111-2222-4333-8444-555555555555',
    deviceId: 'omi-1',
    deviceName: 'Omi',
    codec: 21,
    capturedAtMs: 0,
  };
  const requests: NativeHttpRequest[] = [];
  const record = await openDeviceSession(
    backend(request => {
      requests.push(request);
      return {
        status: 200,
        body: JSON.stringify({session: session({capturedAtMs: 0})}),
      };
    }),
    input,
  );
  expect(record.capturedAtMs).toBe(0);
  expect(record.startedAt).toBe(1);
  expect(JSON.parse(requests[0]!.body!).capturedAtMs).toBe(0);
  await expect(
    openDeviceSession(
      backend(() => ({
        status: 200,
        body: JSON.stringify({session: session({capturedAtMs: 100})}),
      })),
      input,
    ),
  ).rejects.toThrow('recording identity');
});

test.each([null, -1, 0.5, Infinity, 8640000000000001, '1000'])(
  'invalid capture provenance %s cannot be sent or accepted',
  async capturedAtMs => {
    const input = {
      captureId: '11111111-2222-4333-8444-555555555555',
      deviceId: 'omi-1',
      deviceName: 'Omi',
      codec: 21,
    };
    await expect(
      openDeviceSession(
        backend(() => {
          throw Error('must not send');
        }),
        {...input, capturedAtMs: capturedAtMs as number},
      ),
    ).rejects.toThrow('Invalid recording identity');
    await expect(
      openDeviceSession(
        backend(() => ({
          status: 200,
          body: JSON.stringify({session: session({capturedAtMs})}),
        })),
        input,
      ),
    ).rejects.toThrow();
  },
);
