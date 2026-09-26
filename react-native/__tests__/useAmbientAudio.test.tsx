import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';

const mockAudio = {
  requestMicrophonePermission: jest.fn(),
  startAmbientAudio: jest.fn(),
  stopAmbientAudio: jest.fn(async () => undefined),
  ambientAudioStatus: jest.fn(),
};
jest.mock('react-native', () => ({
  NativeModules: {OmiRewind: mockAudio},
  Platform: {OS: 'macos'},
  AppState: {
    addEventListener: jest.fn(() => ({remove: jest.fn()})),
  },
}));
const {useAmbientAudio} = require('../src/app/useAmbientAudio');
let state: ReturnType<typeof useAmbientAudio>;
function Harness({
  mode = 'always',
  sessionReady = true,
}: {
  mode?: 'off' | 'always' | 'meetings';
  sessionReady?: boolean;
}) {
  state = useAmbientAudio(mode, sessionReady);
  return null;
}
let renderer: TestRenderer.ReactTestRenderer;
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockAudio.requestMicrophonePermission.mockResolvedValue('granted');
  mockAudio.startAmbientAudio.mockResolvedValue(undefined);
  mockAudio.ambientAudioStatus.mockResolvedValue({
    running: true,
    sinceMs: 1234,
    chunks: 1,
    bytes: 2048,
    lastError: null,
  });
});
afterEach(async () => {
  await act(async () => renderer?.unmount());
  jest.useRealTimers();
});
async function render(
  mode: 'off' | 'always' | 'meetings' = 'always',
  sessionReady = true,
) {
  await act(async () => {
    renderer = TestRenderer.create(
      <Harness mode={mode} sessionReady={sessionReady} />,
    );
  });
}

test('always mode starts capture and reports running status', async () => {
  await render();
  expect(mockAudio.requestMicrophonePermission).toHaveBeenCalledTimes(1);
  expect(mockAudio.startAmbientAudio).toHaveBeenCalledTimes(1);
  expect(mockAudio.stopAmbientAudio).not.toHaveBeenCalled();
  expect(state.available).toBe(true);
  expect(state.running).toBe(true);
  expect(state.status?.chunks).toBe(1);
});

test('off and meetings modes never start the microphone', async () => {
  await render('off');
  expect(mockAudio.requestMicrophonePermission).not.toHaveBeenCalled();
  await renderer.unmount();
  await render('meetings');
  expect(mockAudio.requestMicrophonePermission).not.toHaveBeenCalled();
  expect(mockAudio.startAmbientAudio).not.toHaveBeenCalled();
});

test('session not ready defers capture until ready', async () => {
  await render('always', false);
  expect(mockAudio.startAmbientAudio).not.toHaveBeenCalled();
  await renderer.unmount();
  await render('always', true);
  expect(mockAudio.startAmbientAudio).toHaveBeenCalledTimes(1);
});

test('denied permission surfaces guidance and never starts', async () => {
  mockAudio.requestMicrophonePermission.mockResolvedValue('denied');
  await render();
  expect(mockAudio.startAmbientAudio).not.toHaveBeenCalled();
  expect(state.error).toBe(
    'Allow Microphone for this app in System Settings, then try again.',
  );
});

test('start failure surfaces guidance without throwing', async () => {
  mockAudio.startAmbientAudio.mockRejectedValueOnce({
    code: 'OMI_CAPTURE_PERMISSION',
  });
  await render();
  expect(state.error).toBe(
    'Allow Microphone for this app in System Settings, then try again.',
  );
  expect(state.running).toBe(false);
});

test('polling refreshes status and disable stops capture', async () => {
  await render();
  mockAudio.ambientAudioStatus.mockResolvedValue({
    running: true,
    sinceMs: 1234,
    chunks: 2,
    bytes: 4096,
    lastError: null,
  });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(5000);
  });
  expect(mockAudio.ambientAudioStatus.mock.calls.length).toBeGreaterThanOrEqual(
    2,
  );
  expect(state.status?.chunks).toBe(2);
  await act(async () => {
    await renderer.unmount();
  });
  await render('off');
  expect(mockAudio.stopAmbientAudio).toHaveBeenCalled();
  expect(state.running).toBe(false);
  expect(state.status).toBe(null);
});
