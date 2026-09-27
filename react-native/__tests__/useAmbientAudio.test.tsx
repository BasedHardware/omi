import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';

const mockAudio = {
  requestMicrophonePermission: jest.fn(),
  startAmbientAudio: jest.fn(async () => undefined),
  stopAmbientAudio: jest.fn(async () => undefined),
  ambientAudioStatus: jest.fn(),
  ambientAudioSegments: jest.fn(),
  ambientAudioSegmentPackets: jest.fn(),
  ambientAudioAcknowledgeSegment: jest.fn(),
};
jest.mock('react-native', () => ({
  NativeModules: {OmiRewind: mockAudio},
  Platform: {OS: 'macos'},
  AppState: {
    addEventListener: jest.fn(() => ({remove: jest.fn()})),
  },
}));
jest.mock('../src/omiNative', () => ({
  omiBackend: {
    createRecordingId: jest.fn(
      async () => '01923f52-3ab6-4c7d-9f8e-6a1b2c3d4e5f',
    ),
    request: jest.fn(),
  },
}));
jest.mock('../src/deviceSessionClient', () => ({
  openDeviceSession: jest.fn(),
  appendDeviceSessionAudio: jest.fn(),
  completeDeviceSession: jest.fn(),
  transcribeDeviceSession: jest.fn(),
  isTransientDeviceSessionError: jest.fn(() => false),
}));

const {useAmbientAudio} = require('../src/app/useAmbientAudio');
const {
  openDeviceSession,
  appendDeviceSessionAudio,
  completeDeviceSession,
  transcribeDeviceSession,
  isTransientDeviceSessionError,
} = require('../src/deviceSessionClient');

const segment = {
  id: 'seg-1700000000000-0123456789abcdef0123456789abcdef.omiseg',
  codec: 20,
  capturedAtMs: 1700000000000,
  packets: 130,
  bytes: 9000,
};
const packet = 'AQIAb3B1cy1wYXlsb2Fk'; // [seq 1][frag 0]["opus-payload"]
let state: ReturnType<typeof useAmbientAudio>;
function Harness({mode = 'always'}: {mode?: 'off' | 'always' | 'meetings'}) {
  state = useAmbientAudio(mode, true);
  return null;
}
let renderer: TestRenderer.ReactTestRenderer;

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockAudio.requestMicrophonePermission.mockResolvedValue('granted');
  mockAudio.ambientAudioStatus.mockResolvedValue({
    running: true,
    sinceMs: 1,
    chunks: 0,
    bytes: 0,
    pendingSegments: 1,
    lastError: null,
  });
  mockAudio.ambientAudioSegments.mockResolvedValue([segment]);
  mockAudio.ambientAudioSegmentPackets.mockImplementation(
    async (_id: string, offset: number, limit: number) => ({
      codec: segment.codec,
      capturedAtMs: segment.capturedAtMs,
      packets: Array.from(
        {length: Math.min(limit, segment.packets - offset)},
        () => packet,
      ),
      total: segment.packets,
      offset,
    }),
  );
  mockAudio.ambientAudioAcknowledgeSegment.mockResolvedValue(undefined);
  (openDeviceSession as jest.Mock).mockResolvedValue({
    id: 'session-1',
    capturedAtMs: segment.capturedAtMs,
    deviceId: 'omi-macos-ambient',
    deviceName: 'This Mac',
    codec: segment.codec,
    state: 'open',
    byteCount: 0,
    chunkCount: 0,
    startedAt: 1,
    endedAt: null,
  });
  (appendDeviceSessionAudio as jest.Mock).mockResolvedValue(undefined);
  (completeDeviceSession as jest.Mock).mockResolvedValue(undefined);
  (transcribeDeviceSession as jest.Mock).mockResolvedValue({
    state: 'queued',
  });
});

afterEach(async () => {
  await act(async () => renderer?.unmount());
  jest.useRealTimers();
});

async function render(props?: {mode?: 'off' | 'always' | 'meetings'}) {
  await act(async () => {
    renderer = TestRenderer.create(<Harness {...props} />);
  });
}

test('always mode starts capture after microphone permission', async () => {
  await render();
  expect(mockAudio.requestMicrophonePermission).toHaveBeenCalled();
  expect(mockAudio.startAmbientAudio).toHaveBeenCalled();
  expect(state.running).toBe(true);
});

test('drains spooled segments in wire-sized batches, then acknowledges', async () => {
  await render();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(1);
  });
  expect(openDeviceSession).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({codec: 20, deviceId: 'omi-macos-ambient'}),
  );
  // 130 packets split into 128 + 2 batches.
  expect(appendDeviceSessionAudio).toHaveBeenCalledTimes(2);
  const firstCall = (appendDeviceSessionAudio as jest.Mock).mock.calls[0][2];
  expect(firstCall).toHaveLength(128);
  expect(mockAudio.ambientAudioAcknowledgeSegment).toHaveBeenCalledWith(
    segment.id,
  );
  expect(completeDeviceSession).toHaveBeenCalledWith(
    expect.anything(),
    'session-1',
  );
  expect(transcribeDeviceSession).toHaveBeenCalledWith(
    expect.anything(),
    'session-1',
  );
});

test('transient failures retry the same segment without acknowledging', async () => {
  (isTransientDeviceSessionError as jest.Mock).mockReturnValue(true);
  (openDeviceSession as jest.Mock).mockRejectedValue(
    Object.assign(new Error('offline'), {status: 503}),
  );
  await render();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(1);
  });
  expect(mockAudio.ambientAudioAcknowledgeSegment).not.toHaveBeenCalled();
  (openDeviceSession as jest.Mock).mockResolvedValue({
    id: 'session-2',
    codec: 20,
    state: 'open',
    byteCount: 0,
    chunkCount: 0,
    startedAt: 1,
    endedAt: null,
  });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(30_000);
  });
  expect(mockAudio.ambientAudioAcknowledgeSegment).toHaveBeenCalledWith(
    segment.id,
  );
});

test('off mode stops native capture but still drains the spool', async () => {
  await render({mode: 'off'});
  expect(mockAudio.startAmbientAudio).not.toHaveBeenCalled();
  expect(mockAudio.stopAmbientAudio).toHaveBeenCalled();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(1);
  });
  expect(openDeviceSession).toHaveBeenCalled();
});
