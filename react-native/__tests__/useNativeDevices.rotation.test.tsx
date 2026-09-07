import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import type {
  NativeHttpRequest,
  NativeSnapshot,
  OmiNativeEvent,
  RecordingJournal,
  RecordingJournalInput,
} from '../src/omiNativeTypes';

const mockRecords: Array<{
  journal: RecordingJournal;
  packets: string[];
  complete: boolean;
}> = [];
let mockListener: ((event: OmiNativeEvent) => void) | null = null;
let mockSnapshot: NativeSnapshot;
const mockNative = {
  getSnapshot: jest.fn(async () => mockSnapshot),
  stopScan: jest.fn(async () => {}),
  connectDevice: jest.fn(async () => {}),
  disconnectDevice: jest.fn(async () => {}),
};
const mockBackend = {
  listRecordingJournals: jest.fn(async () => []),
  readRecordingJournal: jest.fn(),
  createRecordingJournal: jest.fn(async (input: RecordingJournalInput) => {
    const id = `11111111-2222-4333-8444-${String(
      mockRecords.length + 1,
    ).padStart(12, '0')}`;
    const journal: RecordingJournal = {
      handle: id,
      captureId: id,
      sessionId: null,
      deviceId: input.deviceId,
      deviceName: input.deviceName ?? null,
      codec: input.codec,
      entries: [],
    };
    mockRecords.push({journal, packets: [], complete: false});
    return {...journal};
  }),
  appendRecordingJournal: jest.fn(async (handle: string, entry: string) => {
    const record = mockRecords.find(item => item.journal.handle === handle)!;
    record.journal.entries.push(entry);
    return record.journal.entries.length;
  }),
  removeRecordingJournal: jest.fn(async () => {}),
  requestRecordingJournal: jest.fn(
    async (handle: string, request: NativeHttpRequest) => {
      const record = mockRecords.find(item => item.journal.handle === handle)!;
      if (request.path.endsWith('/transcribe'))
        throw new Error('Transcription unavailable');
      record.journal.sessionId ??= record.journal.captureId.replace(
        '11111111',
        '99999999',
      );
      if (request.path.endsWith('/audio')) {
        for (const chunk of JSON.parse(request.body!).chunks) {
          if (chunk.chunkIndex < record.packets.length)
            expect(record.packets[chunk.chunkIndex]).toBe(chunk.bytesBase64);
          else {
            expect(chunk.chunkIndex).toBe(record.packets.length);
            record.packets.push(chunk.bytesBase64);
          }
        }
      }
      if (request.path.endsWith('/complete')) record.complete = true;
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          session: {
            id: record.journal.sessionId,
            deviceId: record.journal.deviceId,
            deviceName: record.journal.deviceName,
            codec: record.journal.codec,
            state: record.complete ? 'complete' : 'open',
            byteCount: record.packets.reduce(
              (total, packet) => total + Buffer.from(packet, 'base64').length,
              0,
            ),
            chunkCount: record.packets.length,
            startedAt: 1,
            endedAt: record.complete ? 2 : null,
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
function Harness({enabled = true}: {enabled?: boolean}) {
  useNativeDevices({enabled});
  return null;
}
async function render() {
  let view: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    view = ReactTestRenderer.create(<Harness />);
  });
  return view!;
}
async function flush(action: () => void) {
  await ReactTestRenderer.act(async () => {
    action();
    for (let index = 0; index < 100; index++) await Promise.resolve();
  });
}
async function emit(event: OmiNativeEvent) {
  await flush(() => mockListener?.(event));
}
function audio(
  sequence: number,
  fragment: number,
  connectionId = 'connection-a',
): Extract<OmiNativeEvent, {type: 'audio'}> {
  return {
    type: 'audio',
    deviceId: 'omi-1',
    connectionId,
    codec: 21,
    payloadBase64: Buffer.from([
      sequence & 255,
      sequence >>> 8,
      fragment,
      42,
    ]).toString('base64'),
  };
}
const press: Extract<OmiNativeEvent, {type: 'button'}> = {
  type: 'button',
  deviceId: 'omi-1',
  connectionId: 'connection-a',
  action: 'doublePress',
};
beforeEach(() => {
  jest.clearAllMocks();
  mockRecords.length = 0;
  mockSnapshot = {
    bluetooth: 'poweredOn',
    devices: [
      {
        id: 'omi-1',
        name: 'Omi',
        connected: true,
        rssi: -30,
        buttonSupported: true,
      },
    ],
    connectedDeviceId: 'omi-1',
    connectionId: 'connection-a',
    phase: 'connected',
    capture: 'recording',
    lastEvent: '',
    microphone: 'unknown',
    notifications: 'unknown',
  };
});

test('double press splits at the next frame boundary exactly once while the prior upload drains', async () => {
  const request = mockBackend.requestRecordingJournal.getMockImplementation()!;
  let release!: () => void;
  mockBackend.requestRecordingJournal.mockImplementationOnce(request);
  mockBackend.requestRecordingJournal.mockImplementationOnce(
    async (handle, value) => {
      await new Promise<void>(resolve => {
        release = resolve;
      });
      return request(handle, value);
    },
  );
  const view = await render();
  try {
    await emit(audio(10, 0));
    await emit(press);
    await emit(press);
    await emit(audio(11, 1));
    expect(mockRecords).toHaveLength(1);
    expect(mockRecords[0]!.complete).toBe(false);
    await emit(audio(12, 0));
    expect(mockRecords).toHaveLength(2);
    expect(mockRecords[1]!.packets).toEqual([audio(12, 0).payloadBase64]);
    expect(mockRecords[1]!.complete).toBe(false);
    expect(mockNative.disconnectDevice).not.toHaveBeenCalled();
    await flush(() => release());
    expect(mockRecords[0]!.packets).toEqual([
      audio(10, 0).payloadBase64,
      audio(11, 1).payloadBase64,
    ]);
    expect(mockRecords[0]!.complete).toBe(true);
    expect(mockRecords[1]!.complete).toBe(false);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
  }
});

test('sequence wrap is preserved and a gap at the requested cut cannot become invisible', async () => {
  const view = await render();
  try {
    await emit(audio(65535, 0));
    await emit(press);
    await emit(audio(0, 0));
    expect(mockRecords).toHaveLength(2);
    await emit(press);
    await emit(audio(3, 0));
    expect(mockRecords).toHaveLength(2);
    expect(mockRecords[1]!.packets).toEqual([
      audio(0, 0).payloadBase64,
      audio(3, 0).payloadBase64,
    ]);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
  }
});

test('empty, stale-connection and leading-fragment presses do not create recordings', async () => {
  const view = await render();
  try {
    await emit(press);
    expect(mockRecords).toHaveLength(0);
    await emit(audio(10, 1));
    await emit(press);
    await emit(audio(11, 0));
    expect(mockRecords).toHaveLength(1);
    await emit({...press, connectionId: 'retired'});
    await emit(audio(12, 0));
    expect(mockRecords).toHaveLength(1);
    await emit(audio(13, 0, 'retired'));
    expect(mockRecords[0]!.packets).toHaveLength(3);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
  }
});

test('a failed capture cannot rotate while its native disconnect is pending', async () => {
  const view = await render();
  try {
    await emit(audio(10, 0));
    await emit(press);
    mockBackend.appendRecordingJournal.mockRejectedValueOnce(
      new Error('disk full'),
    );
    await emit(audio(11, 1));
    expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
    await emit(audio(12, 0));
    expect(mockRecords).toHaveLength(1);
  } finally {
    await ReactTestRenderer.act(async () => view.unmount());
  }
});

test('account retirement clears a pending rotation without completing or opening a capture', async () => {
  const view = await render();
  await emit(audio(10, 0));
  await emit(press);
  const retired = mockListener!;
  await ReactTestRenderer.act(async () =>
    view.update(<Harness enabled={false} />),
  );
  await flush(() => {
    retired(audio(11, 0));
    retired(press);
  });
  expect(mockRecords).toHaveLength(1);
  expect(mockRecords[0]!.complete).toBe(false);
  await ReactTestRenderer.act(async () => view.unmount());
});

test.each(['maxSessionBytes', 'maxChunks'] as const)(
  'automatic rollover reserves a full frame at the %s boundary',
  async limit => {
    const original = DEVICE_UPLOAD_LIMITS[limit];
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, limit, {
      value: limit === 'maxSessionBytes' ? 62_216 : 258,
    });
    const view = await render();
    try {
      await emit(audio(65534, 0));
      await emit(audio(65535, 1));
      expect(mockRecords).toHaveLength(1);
      await emit(audio(0, 0));
      expect(mockRecords).toHaveLength(2);
      expect(mockRecords[0]!.complete).toBe(true);
      expect(mockRecords[0]!.packets).toEqual([
        audio(65534, 0).payloadBase64,
        audio(65535, 1).payloadBase64,
      ]);
      expect(mockRecords[1]!.packets).toEqual([audio(0, 0).payloadBase64]);
      expect(mockNative.disconnectDevice).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(DEVICE_UPLOAD_LIMITS, limit, {value: original});
      await ReactTestRenderer.act(async () => view.unmount());
    }
  },
);

test('automatic rollover cannot conceal a boundary gap or bypass the global pending budget', async () => {
  const original = DEVICE_UPLOAD_LIMITS.maxChunks;
  const pending = DEVICE_UPLOAD_LIMITS.maxPendingBytes;
  Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxChunks', {value: 257});
  const view = await render();
  try {
    await emit(audio(10, 0));
    await emit(audio(12, 0));
    expect(mockRecords).toHaveLength(1);
    expect(mockRecords[0]!.packets).toEqual([
      audio(10, 0).payloadBase64,
      audio(12, 0).payloadBase64,
    ]);
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {value: 3});
    await emit(audio(13, 0));
    expect(mockRecords).toHaveLength(1);
    expect(mockRecords[0]!.packets).toHaveLength(2);
    expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
  } finally {
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxChunks', {value: original});
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {
      value: pending,
    });
    await ReactTestRenderer.act(async () => view.unmount());
  }
});

test('automatic rollover retains the global budget while the preceding upload drains', async () => {
  const chunks = DEVICE_UPLOAD_LIMITS.maxChunks;
  const pending = DEVICE_UPLOAD_LIMITS.maxPendingBytes;
  Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxChunks', {value: 257});
  Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {value: 6});
  const request = mockBackend.requestRecordingJournal.getMockImplementation()!;
  let release!: () => void;
  mockBackend.requestRecordingJournal.mockImplementationOnce(request);
  mockBackend.requestRecordingJournal.mockImplementationOnce(
    async (handle, value) => {
      await new Promise<void>(resolve => {
        release = resolve;
      });
      return request(handle, value);
    },
  );
  const view = await render();
  try {
    await emit(audio(10, 0));
    await emit(audio(11, 0));
    expect(mockRecords).toHaveLength(2);
    expect(mockRecords[1]!.packets).toHaveLength(0);
    expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(1);
    await flush(() => release());
    expect(mockRecords[0]!.packets).toEqual([audio(10, 0).payloadBase64]);
    expect(mockRecords[0]!.complete).toBe(true);
  } finally {
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxChunks', {value: chunks});
    Object.defineProperty(DEVICE_UPLOAD_LIMITS, 'maxPendingBytes', {
      value: pending,
    });
    await ReactTestRenderer.act(async () => view.unmount());
  }
});
