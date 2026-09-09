import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import type {
  NativeHttpRequest,
  NativeSnapshot,
  OmiNativeEvent,
  RecordingJournal,
  RecordingJournalInput,
} from '../src/omiNativeTypes';

// JavaScriptCore's embedded native context has neither browser Base64 global.
const atobDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'atob');
const btoaDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'btoa');
beforeAll(() => {
  Reflect.deleteProperty(globalThis, 'atob');
  Reflect.deleteProperty(globalThis, 'btoa');
});
afterAll(() => {
  if (atobDescriptor) Object.defineProperty(globalThis, 'atob', atobDescriptor);
  if (btoaDescriptor) Object.defineProperty(globalThis, 'btoa', btoaDescriptor);
});

const mockCapture = '11111111-2222-4333-8444-555555555555';
const mockSession = '99999999-2222-4333-8444-555555555555';
const mockSnapshot: NativeSnapshot = {
  bluetooth: 'poweredOn',
  connectionId: 'test-connection',
  devices: [],
  connectedDeviceId: null,
  phase: 'disconnected',
  capture: 'idle',
  lastEvent: '',
  microphone: 'unknown',
  notifications: 'unknown',
};
let mockSaved: RecordingJournal | null = null;
let mockListener: ((event: OmiNativeEvent) => void) | null = null;
const mockNative = {
  getSnapshot: jest.fn(async () => mockSnapshot),
  stopScan: jest.fn(async () => {}),
  connectDevice: jest.fn(async () => {}),
  disconnectDevice: jest.fn(async () => {}),
};
const mockBackend = {
  listRecordingJournals: jest.fn(
    async (): Promise<RecordingJournal[]> =>
      mockSaved === null ? [] : [{...mockSaved, entries: []}],
  ),
  readRecordingJournal: jest.fn(async () => ({
    ...mockSaved!,
    entries: [...mockSaved!.entries],
  })),
  createRecordingJournal: jest.fn(async (input: RecordingJournalInput) => {
    mockSaved = {
      ...(input.capturedAtMs === undefined
        ? {}
        : {capturedAtMs: input.capturedAtMs}),
      handle: mockCapture,
      captureId: mockCapture,
      deviceId: 'omi-1',
      deviceName: null,
      codec: 21,
      sessionId: null,
      entries: [],
    };
    return {...mockSaved};
  }),
  appendRecordingJournal: jest.fn(async (_handle: string, entry: string) => {
    mockSaved!.entries.push(entry);
    return mockSaved!.entries.length;
  }),
  removeRecordingJournal: jest.fn(async () => {
    mockSaved = null;
  }),
  requestRecordingJournal: jest.fn(
    async (_handle: string, request: NativeHttpRequest) => {
      if (request.path.endsWith('/transcribe')) {
        throw new Error('Transcription unavailable');
      }
      mockSaved!.sessionId = mockSession;
      const complete = request.path.endsWith('/complete');
      const index = request.path.endsWith('/audio')
        ? JSON.parse(request.body!).chunks.at(-1).chunkIndex
        : -1;
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          session: {
            ...(mockSaved!.capturedAtMs === undefined
              ? {}
              : {capturedAtMs: mockSaved!.capturedAtMs}),
            id: mockSession,
            deviceId: 'omi-1',
            deviceName: null,
            codec: 21,
            state: complete ? 'complete' : 'open',
            byteCount: (index + 1) * 3,
            chunkCount: index + 1,
            startedAt: 1,
            endedAt: complete ? 2 : null,
          },
        }),
      };
    },
  ),
  request: jest.fn(),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(),
};
jest.mock('../src/omiNative', () => ({
  get omiBackend() {
    return mockBackend;
  },
  get omiNative() {
    return mockNative;
  },
  requestBluetoothScanPermission: async () => true,
  browserScanErrorMessage: () => null,
  subscribeOmiNativeEvents: (listener: (event: OmiNativeEvent) => void) => {
    mockListener = listener;
    return () => {
      mockListener = null;
    };
  },
}));
import {
  DEVICE_UPLOAD_LIMITS,
  useNativeDevices,
} from '../src/app/useNativeDevices';

let state: ReturnType<typeof useNativeDevices>;
function Harness() {
  state = useNativeDevices();
  return null;
}
async function render() {
  let view: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    view = ReactTestRenderer.create(<Harness />);
  });
  return view!;
}
async function emit(event: OmiNativeEvent) {
  await ReactTestRenderer.act(async () => {
    mockListener!(event);
    for (let index = 0; index < 80; index++) {
      await Promise.resolve();
    }
  });
}
const packet: OmiNativeEvent = {
  type: 'audio',
  connectionId: 'test-connection',
  deviceId: 'omi-1',
  codec: 21,
  payloadBase64: 'AAAB',
};
beforeEach(() => {
  jest.clearAllMocks();
  mockSaved = null;
});

test('does not connect until trusted ownership preflight settles', async () => {
  let release!: (value: RecordingJournal[]) => void;
  mockBackend.listRecordingJournals.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  const view = await render();
  let connecting!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    connecting = state.toggleDevice('omi-1', false);
  });
  expect(mockNative.connectDevice).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => {
    release([]);
    await connecting;
  });
  expect(mockNative.connectDevice).toHaveBeenCalledTimes(1);
  await ReactTestRenderer.act(async () => view.unmount());
});

test('packet fsync precedes upload and stop waits for the durable packet', async () => {
  let release!: () => void;
  mockBackend.appendRecordingJournal.mockImplementationOnce(
    async (_handle, entry) => {
      await new Promise<void>(resolve => {
        release = resolve;
      });
      mockSaved!.entries.push(entry);
      return 1;
    },
  );
  const view = await render();
  await emit(packet);
  await emit({type: 'snapshot', snapshot: mockSnapshot});
  expect(mockBackend.requestRecordingJournal).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => {
    release();
    for (let index = 0; index < 100; index++) {
      await Promise.resolve();
    }
  });
  expect(
    mockBackend.requestRecordingJournal.mock.calls.map(call => call[1].path),
  ).toEqual([
    '/v1/device-sessions',
    `/v1/device-sessions/${mockSession}/audio`,
    `/v1/device-sessions/${mockSession}/complete`,
    `/v1/device-sessions/${mockSession}/transcribe`,
  ]);
  expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
  expect(mockBackend.request).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => view.unmount());
});

test('restart recovers the native open acknowledgement lost before JavaScript observed it', async () => {
  let finish!: (
    value: Awaited<ReturnType<typeof mockBackend.requestRecordingJournal>>,
  ) => void;
  mockBackend.requestRecordingJournal.mockImplementationOnce(async () => {
    mockSaved!.sessionId = mockSession;
    return new Promise(resolve => {
      finish = resolve;
    });
  });
  const first = await render();
  await emit(packet);
  expect(mockSaved!.entries).toEqual([JSON.stringify(['p', 'AAAB'])]);
  await ReactTestRenderer.act(async () => first.unmount());
  const second = await render();
  await ReactTestRenderer.act(async () => {
    for (let index = 0; index < 100; index++) {
      await Promise.resolve();
    }
  });
  const calls = mockBackend.requestRecordingJournal.mock.calls;
  expect(
    calls.filter(call => call[1].path === '/v1/device-sessions'),
  ).toHaveLength(1);
  expect(
    JSON.parse(calls.find(call => call[1].path.endsWith('/audio'))![1].body!),
  ).toEqual({chunks: [{chunkIndex: 0, bytesBase64: 'AAAB'}]});
  expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
  await ReactTestRenderer.act(async () => {
    finish({id: 'retired', status: 503, body: '{}'});
    second.unmount();
  });
});

test('offline upload exhaustion continues durable capture without discarding later packets', async () => {
  jest.useFakeTimers();
  const original = mockBackend.requestRecordingJournal.getMockImplementation()!;
  mockBackend.requestRecordingJournal.mockImplementation(async () => {
    throw Object.assign(new Error('offline'), {code: 'OMI_HTTP_TRANSPORT'});
  });
  const view = await render();
  try {
    await emit(packet);
    for (const delay of [500, 1000, 2000]) {
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(delay);
      });
    }
    expect(state.deviceScanMessage).toContain('Upload is paused');
    expect(mockNative.disconnectDevice).not.toHaveBeenCalled();
    await emit({...packet, payloadBase64: 'AAAC'});
    expect(mockSaved!.entries).toEqual([
      JSON.stringify(['p', 'AAAB']),
      JSON.stringify(['p', 'AAAC']),
    ]);
    expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(4);
    await emit({type: 'snapshot', snapshot: mockSnapshot});
    expect(mockSaved!.entries.at(-1)).toBe(JSON.stringify(['s']));
    expect(mockBackend.removeRecordingJournal).not.toHaveBeenCalled();
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
    mockBackend.requestRecordingJournal.mockImplementation(original);
    jest.useRealTimers();
  }
});

test('journal failure after upload pauses stops capture visibly and retains earlier packets', async () => {
  jest.useFakeTimers();
  const original = mockBackend.requestRecordingJournal.getMockImplementation()!;
  mockBackend.requestRecordingJournal.mockImplementation(async () => {
    throw Object.assign(new Error('offline'), {code: 'OMI_HTTP_TRANSPORT'});
  });
  const view = await render();
  try {
    await emit(packet);
    for (const delay of [500, 1000, 2000]) {
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(delay);
      });
    }
    mockBackend.appendRecordingJournal.mockRejectedValueOnce(
      new Error('disk full'),
    );
    await emit({...packet, payloadBase64: 'AAAC'});
    expect(state.deviceScanMessage).toContain('Capture stopped');
    expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
    expect(mockSaved!.entries).toEqual([JSON.stringify(['p', 'AAAB'])]);
    expect(mockBackend.removeRecordingJournal).not.toHaveBeenCalled();
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
    mockBackend.requestRecordingJournal.mockImplementation(original);
    jest.useRealTimers();
  }
});

test('a packet arriving during an older fsync cannot enter that batch or be overtaken by its acknowledgement', async () => {
  const original = mockBackend.appendRecordingJournal.getMockImplementation()!;
  const releases = new Map<string, () => void>();
  const gated = new Set([
    JSON.stringify(['a', 1]),
    JSON.stringify(['p', 'AAAC']),
    JSON.stringify(['p', 'AAAD']),
  ]);
  mockBackend.appendRecordingJournal.mockImplementation(
    async (handle, entry) => {
      if (gated.has(entry))
        await new Promise<void>(resolve => {
          releases.set(entry, resolve);
        });
      return original(handle, entry);
    },
  );
  const view = await render();
  const release = async (entry: unknown[]) => {
    await ReactTestRenderer.act(async () => {
      const resume = releases.get(JSON.stringify(entry));
      expect(resume).toBeDefined();
      resume!();
      for (let index = 0; index < 100; index++) await Promise.resolve();
    });
  };
  try {
    await emit(packet);
    await emit({...packet, payloadBase64: 'AAAC'});
    await release(['a', 1]);
    await emit({...packet, payloadBase64: 'AAAD'});
    await release(['p', 'AAAC']);
    const audio = mockBackend.requestRecordingJournal.mock.calls.filter(call =>
      call[1].path.endsWith('/audio'),
    );
    expect(audio).toHaveLength(2);
    expect(JSON.parse(audio[1]![1].body!)).toEqual({
      chunks: [{chunkIndex: 1, bytesBase64: 'AAAC'}],
    });
    expect(
      mockBackend.appendRecordingJournal.mock.calls.some(
        call => call[1] === JSON.stringify(['a', 2]),
      ),
    ).toBe(false);
    await release(['p', 'AAAD']);
    expect(mockSaved!.entries).toEqual([
      JSON.stringify(['p', 'AAAB']),
      JSON.stringify(['a', 1]),
      JSON.stringify(['p', 'AAAC']),
      JSON.stringify(['p', 'AAAD']),
      JSON.stringify(['a', 2]),
      JSON.stringify(['a', 3]),
    ]);
    await emit({type: 'snapshot', snapshot: mockSnapshot});
    expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
    mockBackend.appendRecordingJournal.mockImplementation(original);
  }
});

test('a failed upload keeps later pending fsync bytes charged across reconnect', async () => {
  const limit = DEVICE_UPLOAD_LIMITS.maxPendingBytes;
  Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {value: 6});
  const originalRequest =
    mockBackend.requestRecordingJournal.getMockImplementation()!;
  const originalAppend =
    mockBackend.appendRecordingJournal.getMockImplementation()!;
  let failUpload!: () => void;
  let finishPacket!: () => void;
  mockBackend.requestRecordingJournal.mockImplementation(
    async (handle, request) => {
      if (request.path.endsWith('/audio') && !failUpload) {
        await new Promise<void>((_resolve, reject) => {
          failUpload = () => reject(new Error('upload rejected'));
        });
      }
      return originalRequest(handle, request);
    },
  );
  mockBackend.appendRecordingJournal.mockImplementation(
    async (handle, entry) => {
      if (entry === JSON.stringify(['p', 'AAAC'])) {
        const saved = mockSaved!;
        await new Promise<void>(resolve => {
          finishPacket = resolve;
        });
        saved.entries.push(entry);
        return saved.entries.length;
      }
      return originalAppend(handle, entry);
    },
  );
  const view = await render();
  try {
    await emit(packet);
    await emit({...packet, payloadBase64: 'AAAC'});
    await ReactTestRenderer.act(async () => {
      failUpload();
      for (let index = 0; index < 60; index++) await Promise.resolve();
    });
    await ReactTestRenderer.act(async () => {
      await state.toggleDevice('omi-1', false);
    });
    await emit({...packet, payloadBase64: 'AAAD'});
    expect(state.deviceScanMessage).toContain('storage limit');
    expect(
      mockBackend.appendRecordingJournal.mock.calls.some(
        call => call[1] === JSON.stringify(['p', 'AAAD']),
      ),
    ).toBe(false);
    await ReactTestRenderer.act(async () => {
      finishPacket();
      for (let index = 0; index < 60; index++) await Promise.resolve();
    });
    await ReactTestRenderer.act(async () => {
      await state.toggleDevice('omi-1', false);
    });
    await emit({...packet, payloadBase64: 'AAAE'});
    expect(
      mockBackend.appendRecordingJournal.mock.calls.some(
        call => call[1] === JSON.stringify(['p', 'AAAE']),
      ),
    ).toBe(true);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {
      value: limit,
    });
    mockBackend.requestRecordingJournal.mockImplementation(originalRequest);
    mockBackend.appendRecordingJournal.mockImplementation(originalAppend);
  }
});

test.each([undefined, 0, 1700000000000])(
  'offline recovery reopens with original optional native capture time %s',
  async capturedAtMs => {
    mockSaved = {
      handle: mockCapture,
      captureId: mockCapture,
      sessionId: null,
      deviceId: 'omi-1',
      deviceName: null,
      codec: 21,
      ...(capturedAtMs === undefined ? {} : {capturedAtMs}),
      entries: [JSON.stringify(['p', 'AAAB']), JSON.stringify(['s'])],
    };
    const view = await render();
    try {
      const open = mockBackend.requestRecordingJournal.mock.calls.find(
        ([, request]) => request.path === '/v1/device-sessions',
      )!;
      const body = JSON.parse(open[1].body!);
      if (capturedAtMs === undefined)
        expect(body).not.toHaveProperty('capturedAtMs');
      else expect(body.capturedAtMs).toBe(capturedAtMs);
      expect(mockBackend.createRecordingJournal).not.toHaveBeenCalled();
    } finally {
      await ReactTestRenderer.act(async () => view.unmount());
    }
  },
);

test.each(['new capture', 'recovered capture'] as const)(
  '%s retains its absent name when discovery changes before open',
  async scenario => {
    let release!: () => void;
    const blocked = new Promise<void>(resolve => {
      release = resolve;
    });
    if (scenario === 'new capture') {
      const create =
        mockBackend.createRecordingJournal.getMockImplementation()!;
      mockBackend.createRecordingJournal.mockImplementationOnce(async input => {
        const journal = await create(input);
        await blocked;
        return journal;
      });
    } else {
      mockSaved = {
        handle: mockCapture,
        captureId: mockCapture,
        deviceId: 'omi-1',
        deviceName: null,
        codec: 21,
        sessionId: null,
        entries: [JSON.stringify(['p', 'AAAB'])],
      };
      const read = mockBackend.readRecordingJournal.getMockImplementation()!;
      mockBackend.readRecordingJournal.mockImplementationOnce(async () => {
        await blocked;
        return read();
      });
    }
    const view = await render();
    try {
      if (scenario === 'new capture') {
        await emit(packet);
      }
      await emit({
        type: 'snapshot',
        snapshot: {
          ...mockSnapshot,
          connectedDeviceId: 'omi-1',
          phase: 'connected',
          capture: 'recording',
          devices: [{id: 'omi-1', name: 'Discovered later', connected: true}],
        },
      });
      expect(mockBackend.requestRecordingJournal).not.toHaveBeenCalled();
      await ReactTestRenderer.act(async () => {
        release();
        for (let index = 0; index < 100; index++) {
          await Promise.resolve();
        }
      });
      const open = mockBackend.requestRecordingJournal.mock.calls.find(
        call => call[1].path === '/v1/device-sessions',
      )!;
      expect(JSON.parse(open[1].body!)).not.toHaveProperty('deviceName');
      await emit({type: 'snapshot', snapshot: mockSnapshot});
      expect(
        mockBackend.requestRecordingJournal.mock.calls.map(
          call => call[1].path,
        ),
      ).toEqual([
        '/v1/device-sessions',
        `/v1/device-sessions/${mockSession}/audio`,
        `/v1/device-sessions/${mockSession}/complete`,
        `/v1/device-sessions/${mockSession}/transcribe`,
      ]);
      expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
    } finally {
      release();
      await ReactTestRenderer.act(async () => view.unmount());
    }
  },
);

test.each(['open', 'audio', 'complete'] as const)(
  'sealed journal automatically resumes after transient %s admission recovers',
  async stage => {
    jest.useFakeTimers();
    const limit = DEVICE_UPLOAD_LIMITS.maxPendingBytes;
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {value: 3});
    const original =
      mockBackend.requestRecordingJournal.getMockImplementation()!;
    let healthy = false;
    const blocked = (path: string) =>
      stage === 'open'
        ? path === '/v1/device-sessions'
        : path.endsWith(`/${stage}`);
    mockBackend.requestRecordingJournal.mockImplementation(
      async (handle, request) =>
        !healthy && blocked(request.path)
          ? {id: request.id, status: 503, body: '{}'}
          : original(handle, request),
    );
    const view = await render();
    try {
      await emit(packet);
      await emit({type: 'snapshot', snapshot: mockSnapshot});
      for (const delay of [500, 1000, 2000]) {
        await ReactTestRenderer.act(async () => {
          await jest.advanceTimersByTimeAsync(delay);
        });
      }
      expect(
        mockBackend.requestRecordingJournal.mock.calls.filter(call =>
          blocked(call[1].path),
        ),
      ).toHaveLength(4);
      expect(mockBackend.removeRecordingJournal).not.toHaveBeenCalled();
      expect(state.deviceScanMessage).toContain('retry automatically');
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(5000 + 3500);
      });
      expect(
        mockBackend.requestRecordingJournal.mock.calls.filter(call =>
          blocked(call[1].path),
        ),
      ).toHaveLength(8);
      healthy = true;
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(10000);
      });
      expect(mockBackend.readRecordingJournal).toHaveBeenCalledWith(
        mockCapture,
      );
      expect(
        mockBackend.requestRecordingJournal.mock.calls.at(-2)?.[1].path,
      ).toBe(`/v1/device-sessions/${mockSession}/complete`);
      expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
      expect(mockSaved).toBeNull();
      const calls = mockBackend.requestRecordingJournal.mock.calls.length;
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(120000);
      });
      expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(calls);
    } finally {
      await ReactTestRenderer.act(async () => view.unmount());
      mockBackend.requestRecordingJournal.mockImplementation(original);
      Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {
        value: limit,
      });
      jest.useRealTimers();
    }
  },
);

test.each(['unmount', 'disable', 'permanent'] as const)(
  '%s does not restart a paused journal upload automatically',
  async mode => {
    jest.useFakeTimers();
    const original =
      mockBackend.requestRecordingJournal.getMockImplementation()!;
    mockBackend.requestRecordingJournal.mockImplementation(
      async (_handle, request) => ({
        id: request.id,
        status: mode === 'permanent' ? 409 : 503,
        body: '{}',
      }),
    );
    function Enabled({enabled}: {enabled: boolean}) {
      state = useNativeDevices({enabled});
      return null;
    }
    let releaseRead: (() => void) | undefined;
    let view!: ReactTestRenderer.ReactTestRenderer;
    await ReactTestRenderer.act(async () => {
      view = ReactTestRenderer.create(<Enabled enabled />);
    });
    try {
      await emit(packet);
      for (const delay of [500, 1000, 2000]) {
        await ReactTestRenderer.act(async () => {
          await jest.advanceTimersByTimeAsync(delay);
        });
      }
      const calls = mockBackend.requestRecordingJournal.mock.calls.length;
      expect(calls).toBe(mode === 'permanent' ? 1 : 4);
      if (mode !== 'permanent') {
        const read = mockBackend.readRecordingJournal.getMockImplementation()!;
        mockBackend.readRecordingJournal.mockImplementationOnce(async () => {
          const saved = await read();
          await new Promise<void>(resolve => {
            releaseRead = resolve;
          });
          return saved;
        });
        await emit({type: 'snapshot', snapshot: mockSnapshot});
        await ReactTestRenderer.act(async () => {
          await jest.advanceTimersByTimeAsync(5000);
        });
        expect(releaseRead).toBeDefined();
      }
      if (mode === 'unmount')
        await ReactTestRenderer.act(async () => view.unmount());
      if (mode === 'disable')
        await ReactTestRenderer.act(async () =>
          view.update(<Enabled enabled={false} />),
        );
      await ReactTestRenderer.act(async () => {
        releaseRead?.();
        await jest.advanceTimersByTimeAsync(120000);
      });
      expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(calls);
      expect(mockBackend.removeRecordingJournal).not.toHaveBeenCalled();
    } finally {
      releaseRead?.();
      await ReactTestRenderer.act(async () => view.unmount());
      mockBackend.requestRecordingJournal.mockImplementation(original);
      jest.useRealTimers();
    }
  },
);

test('active capture resumes without another packet and sustained failures use one capped backoff', async () => {
  jest.useFakeTimers();
  const original = mockBackend.requestRecordingJournal.getMockImplementation()!;
  let healthy = false;
  mockBackend.requestRecordingJournal.mockImplementation(
    async (handle, request) =>
      healthy
        ? original(handle, request)
        : {id: request.id, status: 503, body: '{}'},
  );
  const view = await render();
  try {
    await emit(packet);
    for (const delay of [500, 1000, 2000]) {
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(delay);
      });
    }
    expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(4);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(4999);
    });
    expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(4);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(1 + 3500);
    });
    expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(8);
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(9999);
    });
    expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(8);
    healthy = true;
    await ReactTestRenderer.act(async () => {
      await jest.advanceTimersByTimeAsync(1);
    });
    expect(
      mockBackend.requestRecordingJournal.mock.calls.at(-1)?.[1].path,
    ).toBe(`/v1/device-sessions/${mockSession}/audio`);
    expect(mockBackend.readRecordingJournal).not.toHaveBeenCalled();
    expect(state.deviceScanMessage).toBeNull();
    expect(mockSaved!.entries).toEqual([
      JSON.stringify(['p', 'AAAB']),
      JSON.stringify(['a', 1]),
    ]);
    await emit({type: 'snapshot', snapshot: mockSnapshot});
    expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(1);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
    mockBackend.requestRecordingJournal.mockImplementation(original);
    jest.useRealTimers();
  }
});

test.each([false, true])(
  'stopped retry waits for stop fsync and released reservation before restoring the journal (failure: %s)',
  async fails => {
    jest.useFakeTimers();
    const limit = DEVICE_UPLOAD_LIMITS.maxPendingBytes;
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {value: 3});
    const request =
      mockBackend.requestRecordingJournal.getMockImplementation()!;
    const append = mockBackend.appendRecordingJournal.getMockImplementation()!;
    let healthy = false;
    let releaseStop: (() => void) | undefined;
    mockBackend.requestRecordingJournal.mockImplementation(
      async (handle, input) =>
        healthy
          ? request(handle, input)
          : {id: input.id, status: 503, body: '{}'},
    );
    mockBackend.appendRecordingJournal.mockImplementation(
      async (handle, entry) => {
        if (entry === JSON.stringify(['s'])) {
          await new Promise<void>(resolve => {
            releaseStop = resolve;
          });
        }
        if (fails && entry === JSON.stringify(['s'])) {
          throw new Error('Disk write failed');
        }
        return append(handle, entry);
      },
    );
    const view = await render();
    try {
      await emit(packet);
      for (const delay of [500, 1000, 2000]) {
        await ReactTestRenderer.act(async () => {
          await jest.advanceTimersByTimeAsync(delay);
        });
      }
      await emit({type: 'snapshot', snapshot: mockSnapshot});
      healthy = true;
      await ReactTestRenderer.act(async () => {
        await jest.advanceTimersByTimeAsync(5000);
      });
      expect(mockBackend.readRecordingJournal).not.toHaveBeenCalled();
      await ReactTestRenderer.act(async () => {
        releaseStop!();
        for (let index = 0; index < 100; index++) {
          await Promise.resolve();
        }
      });
      expect(mockBackend.readRecordingJournal).toHaveBeenCalledTimes(
        fails ? 0 : 1,
      );
      expect(mockBackend.removeRecordingJournal).toHaveBeenCalledTimes(
        fails ? 0 : 1,
      );
      if (fails) {
        expect(state.deviceScanMessage).toContain('Recording storage failed');
        await ReactTestRenderer.act(async () => {
          await jest.advanceTimersByTimeAsync(120000);
        });
        expect(mockBackend.requestRecordingJournal).toHaveBeenCalledTimes(4);
        expect(mockSaved).not.toBeNull();
      } else {
        expect(mockSaved).toBeNull();
      }
    } finally {
      releaseStop?.();
      await ReactTestRenderer.act(async () => view.unmount());
      mockBackend.requestRecordingJournal.mockImplementation(request);
      mockBackend.appendRecordingJournal.mockImplementation(append);
      Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {
        value: limit,
      });
      jest.useRealTimers();
    }
  },
);
