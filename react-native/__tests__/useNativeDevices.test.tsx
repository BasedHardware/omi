import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import type {
  Device,
  NativeSnapshot,
  OmiNativeEvent,
} from '../src/omiNativeTypes';

const mockListeners: Array<(event: OmiNativeEvent) => void> = [];

const snapshot = (overrides: Partial<NativeSnapshot> = {}): NativeSnapshot => ({
  bluetooth: 'poweredOn',
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
  connectDevice: jest.fn(async (_id: string): Promise<void> => undefined),
  disconnectDevice: jest.fn(async (_id: string): Promise<void> => undefined),
  getSnapshot: jest.fn(async () => snapshot()),
  startScan: jest.fn(async (_timeout?: number) => [] as Device[]),
};

const mockBackend = {
  request: jest.fn(async (_request: {path: string; body?: string}) => ({
    id: 'req',
    status: 201,
    body: JSON.stringify({
      session: {
        id: '11111111-2222-3333-4444-555555555555',
        deviceId: 'omi-1',
        deviceName: 'Omi',
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
  browserScanErrorMessage: () => null,
  omiBackend: {
    request: (request: {path: string}) => mockBackend.request(request),
    generationEvents: (generationId: string, lastEventId: string | null) =>
      mockBackend.generationEvents(generationId, lastEventId),
    cancelGenerationEvents: (generationId: string) =>
      mockBackend.cancelGenerationEvents(generationId),
  },
  omiNative: {
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
        deviceName: 'Omi',
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

function emitNative(event: OmiNativeEvent) {
  mockListeners.forEach(listener => listener(event));
}

function Harness({
  onState,
}: {
  onState: (state: ReturnType<typeof useNativeDevices>) => void;
}) {
  const state = useNativeDevices();
  onState(state);
  return null;
}

async function renderHook() {
  let latest: ReturnType<typeof useNativeDevices> | null = null;
  await ReactTestRenderer.act(async () => {
    ReactTestRenderer.create(
      <Harness
        onState={state => {
          latest = state;
        }}
      />,
    );
  });
  return {
    latest: () => latest!,
  };
}

beforeEach(() => {
  mockListeners.length = 0;
  mockNative.getSnapshot.mockResolvedValue(snapshot());
  mockNative.startScan.mockReset();
  mockNative.connectDevice.mockReset();
  mockNative.disconnectDevice.mockReset();
  mockNative.connectDevice.mockResolvedValue(undefined);
  mockNative.disconnectDevice.mockResolvedValue(undefined);
  mockBackend.request.mockReset();
  mockBackend.request.mockImplementation(async (request: {path: string}) => {
    if (request.path.endsWith('/complete')) {
      return sessionResponse(200, {state: 'complete', endedAt: 2});
    }
    if (request.path.endsWith('/audio')) {
      return sessionResponse(200, {byteCount: 3, chunkCount: 1});
    }
    return sessionResponse(201);
  });
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
  let resolveAppend: () => void = () => undefined;
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
  mockBackend.request.mockImplementation(async (request: {path: string}) => {
    if (request.path === '/v1/device-sessions') {
      await new Promise<void>(resolve => {
        resolveOpen = resolve;
      });
      return sessionResponse(201);
    }
    if (request.path.endsWith('/audio')) {
      inFlightAppends += 1;
      maxInFlightAppends = Math.max(maxInFlightAppends, inFlightAppends);
      await new Promise<void>(resolve => {
        resolveAppend = resolve;
      });
      inFlightAppends -= 1;
      return sessionResponse(200, {byteCount: 3, chunkCount: 1});
    }
    return sessionResponse(200, {state: 'complete', endedAt: 2});
  });

  const hook = await renderHook();
  expect(mockListeners).toHaveLength(1);

  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
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

  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
      deviceId: 'omi-1',
      codec: 21,
      payloadBase64: 'BwgJ',
    });
  });
  expect(inFlightAppends).toBe(1);

  await ReactTestRenderer.act(async () => {
    resolveAppend();
    await Promise.resolve();
    resolveAppend();
    await Promise.resolve();
    resolveAppend();
    await Promise.resolve();
  });
  expect(maxInFlightAppends).toBe(1);
  expect(
    mockBackend.request.mock.calls.filter(([request]) =>
      request.path.endsWith('/audio'),
    ),
  ).toHaveLength(3);
});

test('completes a session that opens after disconnect', async () => {
  let resolveOpen: () => void = () => undefined;
  mockBackend.request.mockImplementation(async (request: {path: string}) => {
    if (request.path === '/v1/device-sessions') {
      await new Promise<void>(resolve => {
        resolveOpen = resolve;
      });
      return sessionResponse(201);
    }
    if (request.path.endsWith('/complete')) {
      return sessionResponse(200, {state: 'complete', endedAt: 2});
    }
    return sessionResponse(200, {byteCount: 3, chunkCount: 1});
  });

  const hook = await renderHook();
  await ReactTestRenderer.act(async () => {
    emitNative({
      type: 'audio',
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
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(
    mockBackend.request.mock.calls.some(
      ([request]) =>
        request.path ===
        '/v1/device-sessions/11111111-2222-3333-4444-555555555555/complete',
    ),
  ).toBe(true);
  expect(
    mockBackend.request.mock.calls.some(([request]) =>
      request.path.endsWith('/audio'),
    ),
  ).toBe(false);
});
