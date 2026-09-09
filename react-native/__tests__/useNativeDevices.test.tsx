import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import {PermissionsAndroid, Platform} from 'react-native';
import type {
  Device,
  NativeSnapshot,
  OmiNativeEvent,
} from '../src/omiNativeTypes';

const mockListeners: Array<(event: OmiNativeEvent) => void> = [];

const snapshot = (overrides: Partial<NativeSnapshot> = {}): NativeSnapshot => ({
  bluetooth: 'poweredOn',
  connectionId: 'test-connection',
  devices: [],
  connectedDeviceId: null,
  phase: 'disconnected',
  capture: 'idle',
  lastEvent: 'ready',
  microphone: 'unknown',
  notifications: 'unknown',
  ...overrides,
});

const mockNative = {
  getRememberedDevice: jest.fn(
    async (): Promise<{id: string; name: string} | null> => null,
  ),
  rememberConnectedDevice: jest.fn(async () => ({id: 'omi-1', name: 'My Omi'})),
  forgetRememberedDevice: jest.fn(async () => {}),
  stopScan: jest.fn(async (): Promise<void> => undefined),
  connectDevice: jest.fn(async (_id: string): Promise<void> => undefined),
  disconnectDevice: jest.fn(async (_id: string): Promise<void> => undefined),
  getSnapshot: jest.fn(async () => snapshot()),
  startScan: jest.fn(async (_timeout?: number) => [] as Device[]),
};

const mockBackend = {
  createRecordingId: jest.fn(
    async () => '11111111-2222-4333-8444-555555555555',
  ),
  request: jest.fn(async (_request: {path: string; body?: string}) => ({
    id: 'req',
    status: 201,
    body: JSON.stringify({
      session: {
        id: '11111111-2222-3333-4444-555555555555',
        deviceId: 'omi-1',
        deviceName: null,
        codec: 21,
        state: 'open',
        byteCount: 0,
        chunkCount: 0,
        startedAt: 1,
        endedAt: null,
      },
    }),
  })),
  generationEvents: jest.fn(
    async (_generationId: string, _lastEventId: string | null) => ({
      id: '',
      status: 200,
      body: '',
    }),
  ),
  cancelGenerationEvents: jest.fn(async (_generationId: string) => undefined),
};

jest.mock('../src/omiNative', () => ({
  requestBluetoothScanPermission: () =>
    jest.requireActual('../src/omiNative').requestBluetoothScanPermission(),
  browserScanErrorMessage: () => null,
  omiBackend: {
    createRecordingId: () => mockBackend.createRecordingId(),
    request: (request: {path: string}) => mockBackend.request(request),
    generationEvents: (generationId: string, lastEventId: string | null) =>
      mockBackend.generationEvents(generationId, lastEventId),
    cancelGenerationEvents: (generationId: string) =>
      mockBackend.cancelGenerationEvents(generationId),
  },
  omiNative: {
    getRememberedDevice: () => mockNative.getRememberedDevice(),
    rememberConnectedDevice: () => mockNative.rememberConnectedDevice(),
    forgetRememberedDevice: () => mockNative.forgetRememberedDevice(),
    stopScan: () => mockNative.stopScan(),
    connectDevice: (id: string) => mockNative.connectDevice(id),
    disconnectDevice: (id: string) => mockNative.disconnectDevice(id),
    getSnapshot: () => mockNative.getSnapshot(),
    startScan: (timeout?: number) => mockNative.startScan(timeout),
  },
  subscribeOmiNativeEvents: (listener: (event: OmiNativeEvent) => void) => {
    mockListeners.push(listener);
    return () => {
      const index = mockListeners.indexOf(listener);
      if (index >= 0) {
        mockListeners.splice(index, 1);
      }
    };
  },
}));

import {useNativeDevices} from '../src/app/useNativeDevices';

function transcriptResponse(path: string) {
  return {
    id: 'req',
    status: 200,
    body: JSON.stringify({
      transcription: {
        sessionId: path.split('/')[3],
        state: 'completed',
        text: 'Recorded speech',
        segments: [],
        language: null,
        errorCode: null,
        updatedAt: 1,
        discardedLeadingPackets: 0,
      },
    }),
  };
}

function sessionResponse(
  status: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    id: 'req',
    status,
    body: JSON.stringify({
      session: {
        id: '11111111-2222-3333-4444-555555555555',
        deviceId: 'omi-1',
        deviceName: null,
        codec: 21,
        state: 'open',
        byteCount: 0,
        chunkCount: 0,
        startedAt: 1,
        endedAt: null,
        ...overrides,
      },
    }),
  };
}

function audioCounters(request: {body?: string}) {
  const chunkIndex = request.body
    ? JSON.parse(request.body).chunks?.at(-1)?.chunkIndex
    : undefined;
  return typeof chunkIndex === 'number'
    ? {chunkCount: chunkIndex + 1, byteCount: (chunkIndex + 1) * 3}
    : {};
}

function emitNative(event: OmiNativeEvent) {
  mockListeners.forEach(listener => listener(event));
}

async function waitFor(predicate: () => boolean) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) {
      return;
    }
    await Promise.resolve();
  }
  throw new Error('timed out waiting for condition');
}

function Harness({
  enabled,
  onState,
}: {
  enabled?: boolean;
  onState: (state: ReturnType<typeof useNativeDevices>) => void;
}) {
  const state = useNativeDevices(enabled === undefined ? undefined : {enabled});
  onState(state);
  return null;
}

async function renderHook(enabled?: boolean) {
  let latest: ReturnType<typeof useNativeDevices> | null = null;
  let renderer: ReactTestRenderer.ReactTestRenderer;
  const onState = (state: ReturnType<typeof useNativeDevices>) => {
    latest = state;
  };
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(
      <Harness enabled={enabled} onState={onState} />,
    );
  });
  return {
    latest: () => latest!,
    setEnabled: async (value: boolean) => {
      await ReactTestRenderer.act(async () => {
        renderer.update(<Harness enabled={value} onState={onState} />);
      });
    },
    unmount: async () => {
      await ReactTestRenderer.act(async () => {
        renderer.unmount();
      });
    },
  };
}

beforeEach(() => {
  mockListeners.length = 0;
  mockNative.getRememberedDevice.mockReset().mockResolvedValue(null);
  mockNative.rememberConnectedDevice
    .mockReset()
    .mockResolvedValue({id: 'omi-1', name: 'My Omi'});
  mockNative.forgetRememberedDevice.mockReset().mockResolvedValue(undefined);
  mockNative.getSnapshot.mockResolvedValue(snapshot());
  mockNative.startScan.mockReset();
  mockNative.stopScan.mockClear();
  mockNative.connectDevice.mockReset();
  mockNative.disconnectDevice.mockReset();
  mockNative.connectDevice.mockResolvedValue(undefined);
  mockNative.disconnectDevice.mockResolvedValue(undefined);
  mockBackend.createRecordingId.mockReset();
  mockBackend.createRecordingId.mockResolvedValue(
    '11111111-2222-4333-8444-555555555555',
  );
  mockBackend.request.mockReset();
  mockBackend.request.mockImplementation(
    async (request: {path: string; body?: string}) => {
      if (request.path.endsWith('/transcribe'))
        return transcriptResponse(request.path);
      if (request.path.endsWith('/complete')) {
        return sessionResponse(200, {state: 'complete', endedAt: 2});
      }
      if (request.path.endsWith('/audio')) {
        return sessionResponse(200, audioCounters(request));
      }
      return sessionResponse(201);
    },
  );
});

test.each([false, true])(
  'clears a previous device failure when retrying connected=%s',
  async connected => {
    const operation = connected
      ? mockNative.disconnectDevice
      : mockNative.connectDevice;
    operation.mockRejectedValueOnce(new Error('unavailable'));
    const hook = await renderHook();
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', connected);
    });
    expect(hook.latest().deviceScanMessage).toContain('Could not');
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', connected);
    });
    expect(operation).toHaveBeenCalledTimes(2);
    expect(hook.latest().deviceScanMessage).toBeNull();
    await hook.unmount();
  },
);

test('does not probe native devices when the host disables them', async () => {
  mockNative.getSnapshot.mockClear();
  const hook = await renderHook(false);
  expect(hook.latest().nativeSnapshot).toBeNull();
  expect(mockNative.getSnapshot).not.toHaveBeenCalled();
  expect(mockListeners).toHaveLength(0);
});

test.each(['disable', 'unmount'] as const)(
  'retires deferred session opens on %s',
  async retirement => {
    let release: () => void = () => undefined;
    mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
    mockBackend.request.mockImplementationOnce(async () => {
      await new Promise<void>(resolve => {
        release = resolve;
      });
      return sessionResponse(201);
    });
    const hook = await renderHook();
    const audio = {
      type: 'audio' as const,
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    };
    await ReactTestRenderer.act(async () => {
      emitNative(audio);
    });
    if (retirement === 'disable') {
      await hook.setEnabled(false);
      expect(hook.latest().nativeSnapshot).toBeNull();
      await hook.setEnabled(true);
    } else {
      await hook.unmount();
    }
    await ReactTestRenderer.act(async () => {
      release();
    });
    expect(mockBackend.request).toHaveBeenCalledTimes(1);
    if (retirement === 'disable') {
      await ReactTestRenderer.act(async () => {
        emitNative({...audio, payloadBase64: 'BAUG'});
      });
      expect(
        mockBackend.request.mock.calls.map(([request]) => request.path),
      ).toEqual([
        '/v1/device-sessions',
        '/v1/device-sessions',
        '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
      ]);
      expect(mockBackend.request.mock.calls.at(-1)?.[0].body).toContain('BAUG');
    }
  },
);

test('retired upload failure cannot clear or complete the next session', async () => {
  let rejectUpload: () => void = () => undefined;
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockImplementationOnce(async () => sessionResponse(201));
  mockBackend.request.mockImplementationOnce(async () => {
    await new Promise<void>((_resolve, reject) => {
      rejectUpload = () => reject(new Error('retired upload failure'));
    });
    return sessionResponse(200);
  });
  const hook = await renderHook();
  const audio = {
    type: 'audio' as const,
    connectionId: 'test-connection',
    deviceId: 'omi-1',
    codec: 21,
    payloadBase64: 'AQID',
  };
  await ReactTestRenderer.act(async () => {
    emitNative(audio);
    emitNative(audio);
  });
  await hook.setEnabled(false);
  await hook.setEnabled(true);
  await ReactTestRenderer.act(async () => {
    emitNative({...audio, payloadBase64: 'BAUG'});
  });
  await ReactTestRenderer.act(async () => {
    rejectUpload();
  });
  await ReactTestRenderer.act(async () => {
    emitNative({...audio, payloadBase64: 'BwgJ'});
  });
  expect(hook.latest().deviceScanMessage).toBeNull();
  const appends = mockBackend.request.mock.calls.filter(([request]) =>
    request.path.endsWith('/audio'),
  );
  expect(
    appends.flatMap(([request]) =>
      JSON.parse(request.body!).chunks.map(
        (chunk: {bytesBase64: string}) => chunk.bytesBase64,
      ),
    ),
  ).toEqual(['AQID', 'AQID', 'BAUG', 'BwgJ']);
  expect(
    mockBackend.request.mock.calls.some(([request]) =>
      request.path.endsWith('/complete'),
    ),
  ).toBe(false);
});

test('waits for startScan to resolve before clearing the busy flag', async () => {
  let resolveScan: (devices: Device[]) => void = () => undefined;
  mockNative.startScan.mockImplementation(
    () =>
      new Promise<Device[]>(resolve => {
        resolveScan = resolve;
      }),
  );
  mockNative.getSnapshot.mockResolvedValue(
    snapshot({
      devices: [{id: 'omi-1', name: 'Omi', rssi: -40, connected: false}],
    }),
  );
  const hook = await renderHook();

  let scanDone = false;
  await ReactTestRenderer.act(async () => {
    hook
      .latest()
      .scanForOmi()
      .then(() => {
        scanDone = true;
      });
  });
  expect(hook.latest().deviceBusy).toBe(true);
  expect(scanDone).toBe(false);

  await ReactTestRenderer.act(async () => {
    resolveScan([{id: 'omi-1', name: 'Omi', rssi: -40, connected: false}]);
  });
  expect(mockNative.startScan).toHaveBeenCalledWith(8);
  expect(hook.latest().deviceBusy).toBe(false);
  expect(hook.latest().nativeSnapshot?.devices).toEqual([
    {id: 'omi-1', name: 'Omi', rssi: -40, connected: false},
  ]);
});

test('waits for connectDevice and applies discoveries that arrive after scan start', async () => {
  mockNative.connectDevice.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        setTimeout(() => resolve(), 0);
      }),
  );
  const hook = await renderHook();

  await ReactTestRenderer.act(async () => {
    mockListeners.forEach(listener =>
      listener({
        type: 'discovery',
        device: {id: 'omi-2', name: 'Omi', rssi: -62, connected: false},
      }),
    );
  });
  expect(
    hook.latest().nativeSnapshot?.devices.map(device => device.id),
  ).toEqual(['omi-2']);

  await ReactTestRenderer.act(async () => {
    await hook.latest().toggleDevice('omi-2', false);
  });
  expect(mockNative.connectDevice).toHaveBeenCalledWith('omi-2');
  expect(hook.latest().deviceBusy).toBe(false);
});

test('opens a worker session only after a live audio frame, never a transcript', async () => {
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    mockListeners.forEach(listener =>
      listener({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      }),
    );
  });
  await ReactTestRenderer.act(async () => {
    await Promise.resolve();
  });

  expect(mockBackend.request).toHaveBeenCalled();
  const opened = mockBackend.request.mock.calls[0]?.[0] ?? {
    path: '',
    body: '',
  };
  expect(opened.path).toBe('/v1/device-sessions');
  expect(opened.body).not.toContain('transcript');
  expect(hook.latest().nativeSnapshot?.capture).not.toBe('recording');
});

test('keeps uploading after snapshot events and serializes overlapping appends', async () => {
  let resolveOpen: () => void = () => undefined;
  const appendGates: Array<() => void> = [];
  let inFlightAppends = 0;
  let maxInFlightAppends = 0;
  mockNative.getSnapshot.mockResolvedValue(
    snapshot({
      devices: [{id: 'omi-1', name: 'Pendant', rssi: -40, connected: true}],
      connectedDeviceId: 'omi-1',
      phase: 'connected',
      capture: 'recording',
    }),
  );
  mockBackend.request.mockImplementation(
    async (request: {path: string; body?: string}) => {
      if (request.path === '/v1/device-sessions') {
        await new Promise<void>(resolve => {
          resolveOpen = resolve;
        });
        return sessionResponse(201, {deviceName: 'Pendant'});
      }
      if (request.path.endsWith('/audio')) {
        inFlightAppends += 1;
        maxInFlightAppends = Math.max(maxInFlightAppends, inFlightAppends);
        await new Promise<void>(resolve => {
          appendGates.push(resolve);
        });
        inFlightAppends -= 1;
        return sessionResponse(200, audioCounters(request));
      }
      return sessionResponse(200, {state: 'complete', endedAt: 2});
    },
  );

  const hook = await renderHook();
  expect(mockListeners).toHaveLength(1);

  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
    emitNative({
      type: 'snapshot',
      snapshot: snapshot({
        devices: [{id: 'omi-1', name: 'Pendant', rssi: -40, connected: true}],
        connectedDeviceId: 'omi-1',
        phase: 'connected',
        capture: 'recording',
        lastEvent: 'battery 87',
      }),
    });
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'BAUG',
    });
  });
  expect(mockListeners).toHaveLength(1);
  expect(hook.latest().nativeSnapshot?.lastEvent).toBe('battery 87');

  await ReactTestRenderer.act(async () => {
    resolveOpen();
    await Promise.resolve();
  });
  expect(
    mockBackend.request.mock.calls.filter(
      ([request]) => request.path === '/v1/device-sessions',
    ),
  ).toHaveLength(1);
  expect(appendGates).toHaveLength(1);

  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'BwgJ',
    });
  });
  await ReactTestRenderer.act(async () => {
    appendGates.shift()?.();
    await waitFor(() => appendGates.length === 1);
    appendGates.shift()?.();
    await waitFor(() => inFlightAppends === 0);
  });
  expect(maxInFlightAppends).toBe(1);
  expect(
    mockBackend.request.mock.calls.filter(([request]) =>
      request.path.endsWith('/audio'),
    ),
  ).toHaveLength(2);
});

test('drains queued audio before completing a session', async () => {
  let resolveOpen: () => void = () => undefined;
  const appendGates: Array<() => void> = [];
  const order: string[] = [];
  mockBackend.request.mockImplementation(
    async (request: {path: string; body?: string}) => {
      if (request.path.endsWith('/transcribe')) {
        order.push('transcribe');
        return transcriptResponse(request.path);
      }
      if (request.path === '/v1/device-sessions') {
        await new Promise<void>(resolve => {
          resolveOpen = resolve;
        });
        return sessionResponse(201);
      }
      if (request.path.endsWith('/audio')) {
        order.push('audio');
        await new Promise<void>(resolve => {
          appendGates.push(resolve);
        });
        return sessionResponse(200, audioCounters(request));
      }
      order.push('complete');
      return sessionResponse(200, {state: 'complete', endedAt: 2});
    },
  );

  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'BAUG',
    });
  });
  await ReactTestRenderer.act(async () => {
    resolveOpen();
    await waitFor(() => appendGates.length === 1);
  });

  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'BwgJ',
    });
  });
  let disconnectDone = false;
  await ReactTestRenderer.act(async () => {
    hook
      .latest()
      .toggleDevice('omi-1', true)
      .then(() => {
        disconnectDone = true;
      });
  });
  expect(disconnectDone).toBe(false);
  expect(order).toEqual(['audio']);

  await ReactTestRenderer.act(async () => {
    appendGates.shift()?.();
    await waitFor(() => appendGates.length === 1);
    appendGates.shift()?.();
    await waitFor(() => order.includes('complete'));
  });
  expect(order).toEqual(['audio', 'audio', 'complete', 'transcribe']);
  expect(disconnectDone).toBe(true);
});

test.each([
  [false, false],
  [true, false],
  [false, true],
  [true, true],
])(
  'transcription never blocks disconnect and retires its late result when disabled=%s and terminal=%s',
  async (retired, terminal) => {
    let finish!: () => void;
    const prior = mockBackend.request.getMockImplementation()!;
    mockBackend.request.mockImplementation(async request => {
      if (request.path.endsWith('/transcribe')) {
        await new Promise<void>(resolve => {
          finish = resolve;
        });
        if (terminal) {
          return {
            id: 'terminal',
            status: 200,
            body: JSON.stringify({
              transcription: {
                sessionId: request.path.split('/')[3],
                state: 'failed',
                text: null,
                segments: [],
                language: null,
                errorCode: 'attempt_limit',
                updatedAt: 123,
                discardedLeadingPackets: 0,
              },
            }),
          };
        }
        throw new TypeError('Transcription connection lost');
      }
      return prior(request);
    });
    const hook = await renderHook();
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
      await waitFor(() =>
        mockBackend.request.mock.calls.some(([request]) =>
          request.path.endsWith('/audio'),
        ),
      );
    });
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', true);
    });
    expect(hook.latest().deviceBusy).toBe(false);
    expect(hook.latest().deviceScanMessage).toBe(
      'Recording saved. Transcription is in progress.',
    );
    if (retired) await hook.setEnabled(false);
    await ReactTestRenderer.act(async () => {
      finish();
    });
    if (retired) expect(hook.latest().deviceScanMessage).toBeNull();
    else
      expect(hook.latest().deviceScanMessage).toBe(
        terminal
          ? 'Recording saved, but transcription failed. Open its transcript for details.'
          : 'Recording saved, but transcription could not finish. Open its transcript to check its status.',
      );
    expect(
      mockBackend.request.mock.calls.filter(([request]) =>
        request.path.endsWith('/transcribe'),
      ),
    ).toHaveLength(1);
    await hook.unmount();
  },
);

test('completes a session that opens after disconnect', async () => {
  let resolveOpen: () => void = () => undefined;
  mockBackend.request.mockImplementation(
    async (request: {path: string; body?: string}) => {
      if (request.path === '/v1/device-sessions') {
        await new Promise<void>(resolve => {
          resolveOpen = resolve;
        });
        return sessionResponse(201);
      }
      if (request.path.endsWith('/complete')) {
        return sessionResponse(200, {state: 'complete', endedAt: 2});
      }
      return sessionResponse(200, audioCounters(request));
    },
  );

  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  await ReactTestRenderer.act(async () => {
    await hook.latest().toggleDevice('omi-1', true);
  });
  expect(
    mockBackend.request.mock.calls.some(([request]) =>
      request.path.endsWith('/complete'),
    ),
  ).toBe(false);

  await ReactTestRenderer.act(async () => {
    resolveOpen();
    await waitFor(() =>
      mockBackend.request.mock.calls.some(([request]) =>
        request.path.endsWith('/complete'),
      ),
    );
  });
  const paths = mockBackend.request.mock.calls.map(([request]) => request.path);
  expect(paths).toContain(
    '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
  );
  expect(paths).toContain(
    '/v1/device-sessions/11111111-2222-3333-4444-555555555555/complete',
  );
  expect(
    paths.indexOf(
      '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
    ),
  ).toBeLessThan(
    paths.indexOf(
      '/v1/device-sessions/11111111-2222-3333-4444-555555555555/complete',
    ),
  );
});

test('an ambiguous audio failure stays visible and never completes or retries the recording', async () => {
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockImplementation(
    async (request: {path: string; body?: string}) => {
      if (request.path.endsWith('/audio')) {
        throw new Error('Connection lost after upload');
      }
      return sessionResponse(201);
    },
  );
  const hook = await renderHook();
  const audio = {
    type: 'audio' as const,
    connectionId: 'test-connection',
    deviceId: 'omi-1',
    codec: 21,
    payloadBase64: 'AQID',
  };
  await ReactTestRenderer.act(async () => {
    emitNative(audio);
  });
  expect(hook.latest().deviceScanMessage).toContain(
    'could not be saved completely',
  );
  await ReactTestRenderer.act(async () => {
    emitNative(audio);
    await hook.latest().toggleDevice('omi-1', true);
  });
  expect(
    mockBackend.request.mock.calls.filter(([request]) =>
      request.path.endsWith('/audio'),
    ),
  ).toHaveLength(1);
  expect(
    mockBackend.request.mock.calls.some(([request]) =>
      request.path.endsWith('/complete'),
    ),
  ).toBe(false);

  await ReactTestRenderer.act(async () => {
    await hook.latest().toggleDevice('omi-1', false);
    emitNative(audio);
  });
  expect(
    mockBackend.request.mock.calls.filter(
      ([request]) => request.path === '/v1/device-sessions',
    ),
  ).toHaveLength(2);
});

test.each([false, true])(
  'Android scans only after Bluetooth permission is granted: %s',
  async granted => {
    const os = Object.getOwnPropertyDescriptor(Platform, 'OS')!;
    const version = Object.getOwnPropertyDescriptor(Platform, 'Version')!;
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: 'android',
    });
    Object.defineProperty(Platform, 'Version', {configurable: true, value: 35});
    const permissions = jest
      .spyOn(PermissionsAndroid, 'requestMultiple')
      .mockImplementation(
        async requested =>
          Object.fromEntries(
            requested.map(permission => [
              permission,
              granted ? 'granted' : 'denied',
            ]),
          ) as Awaited<ReturnType<typeof PermissionsAndroid.requestMultiple>>,
      );
    mockNative.startScan.mockResolvedValue([]);
    try {
      const hook = await renderHook();
      await ReactTestRenderer.act(async () => {
        await hook.latest().scanForOmi();
      });
      expect(permissions).toHaveBeenCalledWith([
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      ]);
      expect(mockNative.startScan).toHaveBeenCalledTimes(granted ? 1 : 0);
      expect(hook.latest().deviceBusy).toBe(false);
      if (!granted) {
        expect(hook.latest().deviceScanMessage).toContain(
          'Bluetooth permission is required',
        );
      }
    } finally {
      permissions.mockRestore();
      Object.defineProperty(Platform, 'OS', os);
      Object.defineProperty(Platform, 'Version', version);
    }
  },
);

test.each(['open', 'audio', 'complete'] as const)(
  'user reconnect after natural disconnect isolates a pending %s',
  async stage => {
    const firstId = '11111111-2222-3333-4444-555555555555';
    const secondId = '22222222-2222-3333-4444-555555555555';
    let opens = 0;
    let release: () => void = () => undefined;
    let blocked = false;
    mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
    mockBackend.request.mockImplementation(async request => {
      const opening = request.path === '/v1/device-sessions';
      const id = opening
        ? ++opens === 1
          ? firstId
          : secondId
        : request.path.split('/')[3];
      const action = opening ? 'open' : request.path.split('/')[4];
      if (action === 'transcribe') return transcriptResponse(request.path);
      if (id === firstId && action === stage && !blocked) {
        blocked = true;
        await new Promise<void>(resolve => {
          release = resolve;
        });
      }
      return sessionResponse(opening ? 201 : 200, {
        ...audioCounters(request),
        id,
        state: action === 'complete' ? 'complete' : 'open',
        endedAt: action === 'complete' ? 2 : null,
      });
    });
    const hook = await renderHook();
    const audio = {
      type: 'audio' as const,
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    };
    await ReactTestRenderer.act(async () => {
      emitNative(audio);
    });
    await ReactTestRenderer.act(async () => {
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    expect(blocked).toBe(true);
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', false);
      emitNative({...audio, payloadBase64: 'BAUG'});
    });
    expect(opens).toBe(2);
    await ReactTestRenderer.act(async () => {
      release();
    });
    const appends = mockBackend.request.mock.calls.filter(([request]) =>
      request.path.endsWith('/audio'),
    );
    expect(
      appends.map(([request]) => [
        request.path.split('/')[3],
        JSON.parse(request.body!).chunks[0].bytesBase64,
      ]),
    ).toEqual(
      stage === 'open'
        ? [
            [secondId, 'BAUG'],
            [firstId, 'AQID'],
          ]
        : [
            [firstId, 'AQID'],
            [secondId, 'BAUG'],
          ],
    );
    expect(
      mockBackend.request.mock.calls
        .filter(([request]) => request.path.endsWith('/complete'))
        .map(([request]) => request.path),
    ).toEqual([`/v1/device-sessions/${firstId}/complete`]);
    await ReactTestRenderer.act(async () => {
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    expect(
      mockBackend.request.mock.calls.filter(([request]) =>
        request.path.endsWith('/complete'),
      ),
    ).toHaveLength(2);
    expect(hook.latest().deviceScanMessage).toBeNull();
    await hook.unmount();
  },
);

test.each([false, true])(
  'completion failure is visible unless auth retired: %s',
  async retired => {
    let rejectComplete: () => void = () => undefined;
    mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
    mockBackend.request.mockImplementation(async request => {
      if (request.path.endsWith('/complete')) {
        await new Promise<void>((_resolve, reject) => {
          rejectComplete = () => reject(new Error('Completion unavailable'));
        });
      }
      return sessionResponse(
        request.path === '/v1/device-sessions' ? 201 : 200,
        audioCounters(request),
      );
    });
    const hook = await renderHook();
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
    });
    await ReactTestRenderer.act(async () => {
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    if (retired) {
      await hook.setEnabled(false);
    }
    await ReactTestRenderer.act(async () => {
      rejectComplete();
    });
    if (retired) {
      expect(hook.latest().deviceScanMessage).toBeNull();
    } else {
      expect(hook.latest().deviceScanMessage).toContain(
        'saved status is unconfirmed',
      );
    }
    expect(
      mockBackend.request.mock.calls.filter(([request]) =>
        request.path.endsWith('/complete'),
      ),
    ).toHaveLength(1);
    await hook.unmount();
  },
);

test('retries the same indexed batch before sending later packets or completing', async () => {
  jest.useFakeTimers();
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  let appends = 0;
  mockBackend.request.mockImplementation(async request => {
    if (request.path.endsWith('/transcribe'))
      return transcriptResponse(request.path);
    if (request.path.endsWith('/audio') && ++appends === 1) {
      return {
        id: 'req',
        status: 503,
        body: JSON.stringify({error: {code: 'upload_unavailable'}}),
      };
    }
    return sessionResponse(request.path === '/v1/device-sessions' ? 201 : 200, {
      ...audioCounters(request),
      state: request.path.endsWith('/complete') ? 'complete' : 'open',
    });
  });
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'BAUG',
      });
    });
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'BwgJ',
      });
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    expect(appends).toBe(1);
    expect(
      mockBackend.request.mock.calls.some(([request]) =>
        request.path.endsWith('/complete'),
      ),
    ).toBe(false);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(500);
    });
    expect(
      mockBackend.request.mock.calls
        .filter(([request]) => request.path.endsWith('/audio'))
        .map(([request]) => JSON.parse(request.body!).chunks)
        .flat(),
    ).toEqual([
      {chunkIndex: 0, bytesBase64: 'AQID'},
      {chunkIndex: 1, bytesBase64: 'BAUG'},
      {chunkIndex: 0, bytesBase64: 'AQID'},
      {chunkIndex: 1, bytesBase64: 'BAUG'},
      {chunkIndex: 2, bytesBase64: 'BwgJ'},
    ]);
    expect(mockBackend.request.mock.calls.at(-1)?.[0].path).toMatch(
      /\/transcribe$/,
    );
    expect(hook.latest().deviceScanMessage).toBeNull();
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test.each([401, 409, 413, 503])(
  'upload status %s has bounded retry semantics',
  async status => {
    jest.useFakeTimers();
    mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
    mockBackend.request.mockImplementation(async request =>
      request.path.endsWith('/audio')
        ? {id: 'req', status, body: '{}'}
        : sessionResponse(201),
    );
    const hook = await renderHook();
    try {
      await ReactTestRenderer.act(async () => {
        emitNative({
          type: 'audio',
          connectionId: 'test-connection',
          deviceId: 'omi-1',
          codec: 21,
          payloadBase64: 'AQID',
        });
      });
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(5000);
      });
      expect(
        mockBackend.request.mock.calls.filter(([request]) =>
          request.path.endsWith('/audio'),
        ),
      ).toHaveLength(status === 503 ? 4 : 1);
      expect(hook.latest().deviceScanMessage).toContain(
        'could not be saved completely',
      );
      expect(jest.getTimerCount()).toBe(0);
      await ReactTestRenderer.act(async () => {
        emitNative({type: 'snapshot', snapshot: snapshot()});
      });
      expect(
        mockBackend.request.mock.calls.some(([request]) =>
          request.path.endsWith('/complete'),
        ),
      ).toBe(false);
    } finally {
      await hook.unmount();
      jest.useRealTimers();
    }
  },
);

test('auth retirement cancels delayed retries and starts the next account at index zero', async () => {
  jest.useFakeTimers();
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockImplementationOnce(async () => sessionResponse(201));
  mockBackend.request.mockImplementationOnce(async () => {
    throw Object.assign(new Error('network'), {code: 'OMI_HTTP_TRANSPORT'});
  });
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
    });
    await hook.setEnabled(false);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(0);
    });
    expect(jest.getTimerCount()).toBe(0);
    await hook.setEnabled(true);
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'BAUG',
      });
      await jest.advanceTimersByTimeAsync(5000);
    });
    expect(
      mockBackend.request.mock.calls
        .filter(([request]) => request.path.endsWith('/audio'))
        .map(([request]) => JSON.parse(request.body!).chunks)
        .flat(),
    ).toEqual([
      {chunkIndex: 0, bytesBase64: 'AQID'},
      {chunkIndex: 0, bytesBase64: 'BAUG'},
    ]);
    expect(hook.latest().deviceScanMessage).toBeNull();
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test('bounds buffered audio while recording identity is being created', async () => {
  let release: () => void = () => undefined;
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.createRecordingId.mockImplementationOnce(async () => {
    await new Promise<void>(resolve => {
      release = resolve;
    });
    return '11111111-2222-4333-8444-555555555555';
  });
  const hook = await renderHook();
  const payloadBase64 = Buffer.alloc(1_048_576).toString('base64');
  await ReactTestRenderer.act(async () => {
    for (let count = 0; count < 9; count += 1) {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64,
      });
    }
  });
  expect(hook.latest().deviceScanMessage).toContain('storage limit reached');
  await ReactTestRenderer.act(async () => {
    release();
  });
  expect(mockBackend.request).not.toHaveBeenCalled();
  await hook.unmount();
});

test('retries idempotent completion on a transient transport failure', async () => {
  jest.useFakeTimers();
  let completions = 0;
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockImplementation(async request => {
    if (request.path.endsWith('/transcribe'))
      return transcriptResponse(request.path);
    if (request.path.endsWith('/complete') && ++completions === 1) {
      throw new TypeError('Failed to fetch');
    }
    return sessionResponse(request.path === '/v1/device-sessions' ? 201 : 200, {
      ...audioCounters(request),
      state: request.path.endsWith('/complete') ? 'complete' : 'open',
    });
  });
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
    });
    await ReactTestRenderer.act(async () => {
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    expect(completions).toBe(1);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(500);
    });
    expect(completions).toBe(2);
    expect(hook.latest().deviceScanMessage).toBeNull();
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test('bounds recording open retries and retains the original capture identity', async () => {
  jest.useFakeTimers();
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockRejectedValue(new TypeError('Open response lost'));
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
      await jest.advanceTimersByTimeAsync(5000);
    });
    expect(mockBackend.request).toHaveBeenCalledTimes(4);
    expect(mockBackend.createRecordingId).toHaveBeenCalledTimes(1);
    expect(
      new Set(mockBackend.request.mock.calls.map(([request]) => request.body))
        .size,
    ).toBe(1);
    expect(
      JSON.parse(mockBackend.request.mock.calls[0]![0].body!).captureId,
    ).toBe('11111111-2222-4333-8444-555555555555');
    expect(hook.latest().deviceScanMessage).toContain('could not start');
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test('recovers a lost open response before draining and completing the capture', async () => {
  jest.useFakeTimers();
  let opens = 0;
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  mockBackend.request.mockImplementation(async request => {
    if (request.path.endsWith('/transcribe'))
      return transcriptResponse(request.path);
    if (request.path === '/v1/device-sessions' && ++opens === 1) {
      throw new TypeError('Open response lost');
    }
    return sessionResponse(200, {
      ...audioCounters(request),
      state: request.path.endsWith('/complete') ? 'complete' : 'open',
    });
  });
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
    });
    await ReactTestRenderer.act(async () => {
      emitNative({type: 'snapshot', snapshot: snapshot()});
    });
    expect(mockBackend.request).toHaveBeenCalledTimes(1);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(500);
    });
    const requests = mockBackend.request.mock.calls.map(([request]) => request);
    expect(requests.map(request => request.path.split('/').pop())).toEqual([
      'device-sessions',
      'device-sessions',
      'audio',
      'complete',
      'transcribe',
    ]);
    expect(requests[1]?.body).toBe(requests[0]?.body);
    expect(mockBackend.createRecordingId).toHaveBeenCalledTimes(1);
    expect(hook.latest().deviceScanMessage).toBeNull();
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test('retires a recording identity request when authentication is disabled', async () => {
  let release: (id: string) => void = () => undefined;
  mockBackend.createRecordingId.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  await hook.setEnabled(false);
  await ReactTestRenderer.act(async () => {
    release('11111111-2222-4333-8444-555555555555');
  });
  expect(mockBackend.request).not.toHaveBeenCalled();
  await hook.unmount();
});

test('cancels open retry backoff after authentication is disabled', async () => {
  jest.useFakeTimers();
  mockBackend.request.mockRejectedValue(new TypeError('Open response lost'));
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      emitNative({
        type: 'audio',
        connectionId: 'test-connection',
        deviceId: 'omi-1',
        codec: 21,
        payloadBase64: 'AQID',
      });
    });
    await hook.setEnabled(false);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(5000);
    });
    expect(mockBackend.request).toHaveBeenCalledTimes(1);
    expect(mockBackend.createRecordingId).toHaveBeenCalledTimes(1);
  } finally {
    await hook.unmount();
    jest.useRealTimers();
  }
});

test('rejects an invalid native recording identity before opening', async () => {
  mockBackend.createRecordingId.mockResolvedValue('not-a-uuid');
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  expect(mockBackend.createRecordingId).toHaveBeenCalledTimes(1);
  expect(mockBackend.request).not.toHaveBeenCalled();
  expect(hook.latest().deviceScanMessage).toContain('could not start');
  await hook.unmount();
});

test('native unsupported capture opens do not ask to reconnect', async () => {
  mockBackend.request.mockRejectedValue({code: 'OMI_DEV_BACKEND_UNSUPPORTED'});
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  expect(mockBackend.request).toHaveBeenCalledTimes(1);
  expect(hook.latest().deviceScanMessage).toBe(
    'Audio capture is not available from this backend yet.',
  );
  expect(hook.latest().deviceScanMessage).not.toContain('Reconnect');
  await hook.unmount();
});

test('nested non-retryable capture opens do not ask to reconnect', async () => {
  mockBackend.request.mockResolvedValue({
    id: 'req',
    status: 503,
    body: JSON.stringify({
      error: {
        code: 'development_backend_unsupported',
        retryable: false,
        action: 'none',
      },
    }),
  });
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  expect(hook.latest().deviceScanMessage).toBe(
    'Audio capture is not available from this backend yet.',
  );
  expect(hook.latest().deviceScanMessage).not.toContain('Reconnect');
  await hook.unmount();
});

test('nested non-retryable capture store 503s do not ask to reconnect', async () => {
  mockBackend.request.mockResolvedValue({
    id: 'req',
    status: 503,
    body: JSON.stringify({
      error: {
        code: 'service_unavailable',
        retryable: false,
        action: 'none',
      },
    }),
  });
  mockNative.getSnapshot.mockResolvedValue(snapshot({capture: 'recording'}));
  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      connectionId: 'test-connection',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'AQID',
    });
  });
  expect(hook.latest().deviceScanMessage).toBe(
    'Audio capture is not available from this backend yet.',
  );
  expect(hook.latest().deviceScanMessage).not.toContain('Reconnect');
  await hook.unmount();
});

test('disabling authenticated devices stops scanning and disconnects the current device', async () => {
  mockNative.getSnapshot.mockResolvedValue(
    snapshot({connectedDeviceId: 'omi-1'}),
  );
  const hook = await renderHook();
  await hook.setEnabled(false);
  expect(mockNative.stopScan).toHaveBeenCalledTimes(1);
  expect(mockNative.disconnectDevice).toHaveBeenCalledWith('omi-1');
  await hook.unmount();
  expect(mockNative.stopScan).toHaveBeenCalledTimes(1);
});

test('disabling pending setup disconnects its requested device and late settlement cannot retire a new session', async () => {
  let settle!: () => void;
  mockNative.connectDevice.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        settle = resolve;
      }),
  );
  const hook = await renderHook();
  let connecting!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    connecting = hook.latest().toggleDevice('old-device', false);
  });
  await hook.setEnabled(false);
  expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
  expect(mockNative.disconnectDevice).toHaveBeenCalledWith('old-device');
  await hook.setEnabled(true);
  await ReactTestRenderer.act(async () => {
    await hook.latest().toggleDevice('new-device', false);
  });
  const probes = mockNative.getSnapshot.mock.calls.length;
  await ReactTestRenderer.act(async () => {
    settle();
    await connecting;
  });
  expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
  expect(mockNative.getSnapshot.mock.calls.length).toBe(probes);
  await hook.unmount();
  expect(mockNative.disconnectDevice).toHaveBeenLastCalledWith('new-device');
});

test('disabling an in-flight scan stops native discovery and ignores its late result', async () => {
  let settle!: (devices: Device[]) => void;
  mockNative.startScan.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        settle = resolve;
      }),
  );
  const hook = await renderHook();
  let scanning!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    scanning = hook.latest().scanForOmi();
  });
  expect(mockNative.startScan).toHaveBeenCalledTimes(1);
  await hook.setEnabled(false);
  expect(mockNative.stopScan).toHaveBeenCalledTimes(1);
  const probes = mockNative.getSnapshot.mock.calls.length;
  await ReactTestRenderer.act(async () => {
    settle([]);
    await scanning;
  });
  expect(mockNative.getSnapshot.mock.calls.length).toBe(probes);
  expect(hook.latest().nativeSnapshot).toBeNull();
  expect(hook.latest().deviceBusy).toBe(false);
  await hook.unmount();
});

test('loads a remembered shortcut without scanning or connecting and clears it on account retirement', async () => {
  mockNative.getRememberedDevice.mockResolvedValue({
    id: 'omi-1',
    name: 'My Omi',
  });
  const hook = await renderHook();
  try {
    expect(hook.latest().rememberedDevice).toEqual({
      id: 'omi-1',
      name: 'My Omi',
    });
    expect(mockNative.startScan).not.toHaveBeenCalled();
    expect(mockNative.connectDevice).not.toHaveBeenCalled();
    await hook.setEnabled(false);
    expect(hook.latest().rememberedDevice).toBeNull();
    let finish!: (value: {id: string; name: string}) => void;
    mockNative.getRememberedDevice.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve;
        }),
    );
    await hook.setEnabled(true);
    await hook.setEnabled(false);
    await ReactTestRenderer.act(async () =>
      finish({id: 'old', name: 'Old account'}),
    );
    expect(hook.latest().rememberedDevice).toBeNull();
  } finally {
    await hook.unmount();
  }
});

test('remembers only explicit audio-ready connections and Forget cannot be undone by repeated snapshots', async () => {
  const hook = await renderHook();
  const ready = snapshot({
    phase: 'connected',
    capture: 'recording',
    connectedDeviceId: 'omi-1',
    devices: [{id: 'omi-1', name: 'My Omi', connected: true, rssi: -30}],
  });
  try {
    await ReactTestRenderer.act(async () =>
      emitNative({type: 'snapshot', snapshot: ready}),
    );
    expect(mockNative.rememberConnectedDevice).not.toHaveBeenCalled();
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', false);
    });
    expect(mockNative.rememberConnectedDevice).not.toHaveBeenCalled();
    await ReactTestRenderer.act(async () =>
      emitNative({type: 'snapshot', snapshot: ready}),
    );
    expect(mockNative.rememberConnectedDevice).toHaveBeenCalledTimes(1);
    expect(hook.latest().rememberedDevice?.id).toBe('omi-1');
    await ReactTestRenderer.act(async () => {
      await hook.latest().forgetRememberedDevice();
    });
    expect(hook.latest().rememberedDevice).toBeNull();
    await ReactTestRenderer.act(async () =>
      emitNative({type: 'snapshot', snapshot: ready}),
    );
    expect(mockNative.rememberConnectedDevice).toHaveBeenCalledTimes(1);
    await ReactTestRenderer.act(async () =>
      emitNative({
        type: 'snapshot',
        snapshot: {...ready, connectionId: 'automatic-reconnect'},
      }),
    );
    expect(mockNative.rememberConnectedDevice).toHaveBeenCalledTimes(1);
    expect(hook.latest().rememberedDevice).toBeNull();
    expect(mockNative.disconnectDevice).not.toHaveBeenCalled();
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', false);
    });
    await ReactTestRenderer.act(async () =>
      emitNative({
        type: 'snapshot',
        snapshot: {...ready, connectionId: 'explicit-reconnect'},
      }),
    );
    expect(mockNative.rememberConnectedDevice).toHaveBeenCalledTimes(2);
    expect(hook.latest().rememberedDevice?.id).toBe('omi-1');
  } finally {
    await hook.unmount();
  }
});

test('Forget fences a pending remembered-device lookup and failed deletion retains the shortcut', async () => {
  let finish!: (value: {id: string; name: string}) => void;
  mockNative.getRememberedDevice.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  const hook = await renderHook();
  try {
    await ReactTestRenderer.act(async () => {
      await hook.latest().forgetRememberedDevice();
    });
    await ReactTestRenderer.act(async () =>
      finish({id: 'omi-1', name: 'Stale'}),
    );
    expect(hook.latest().rememberedDevice).toBeNull();
    await hook.setEnabled(false);
    mockNative.getRememberedDevice.mockResolvedValue({
      id: 'omi-1',
      name: 'My Omi',
    });
    await hook.setEnabled(true);
    mockNative.forgetRememberedDevice.mockRejectedValueOnce(
      new Error('storage error'),
    );
    await ReactTestRenderer.act(async () => {
      await hook.latest().forgetRememberedDevice();
    });
    expect(hook.latest().rememberedDevice?.id).toBe('omi-1');
    expect(hook.latest().deviceScanMessage).toContain('could not be forgotten');
  } finally {
    await hook.unmount();
  }
});

test('remembered reconnect checks current native ownership before connecting', async () => {
  mockNative.getRememberedDevice.mockResolvedValue({
    id: 'omi-1',
    name: 'My Omi',
  });
  const hook = await renderHook();
  try {
    mockNative.getRememberedDevice.mockResolvedValueOnce(null);
    await ReactTestRenderer.act(async () => {
      await hook.latest().toggleDevice('omi-1', false);
    });
    expect(mockNative.connectDevice).not.toHaveBeenCalled();
    expect(hook.latest().rememberedDevice).toBeNull();
    expect(hook.latest().deviceScanMessage).toContain('Could not connect');
  } finally {
    await hook.unmount();
  }
});
