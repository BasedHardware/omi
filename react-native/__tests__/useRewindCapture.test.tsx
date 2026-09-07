import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';

const mockCapture = {
  requestCapturePermission: jest.fn(),
  startCapture: jest.fn(async () => undefined),
  stopCapture: jest.fn(async () => undefined),
  captureFrame: jest.fn(),
};
jest.mock('react-native', () => ({
  NativeModules: {OmiRewind: mockCapture},
  Platform: {OS: 'macos'},
}));
const {useRewindCapture} = require('../src/app/useRewindCapture');
let state: ReturnType<typeof useRewindCapture>;
const captured = jest.fn();
function Harness({enabled = true}: {enabled?: boolean}) {
  state = useRewindCapture(enabled, captured);
  return null;
}
let renderer: TestRenderer.ReactTestRenderer;
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockCapture.requestCapturePermission.mockResolvedValue('granted');
  mockCapture.captureFrame.mockResolvedValue({captured: true});
});
afterEach(async () => {
  await act(async () => renderer?.unmount());
  jest.useRealTimers();
});
async function render() {
  await act(async () => {
    renderer = TestRenderer.create(<Harness />);
  });
}

test('capture starts only explicitly and serializes cadence until stopped', async () => {
  await render();
  expect(mockCapture.requestCapturePermission).not.toHaveBeenCalled();
  let release!: (value: {captured: boolean}) => void;
  mockCapture.captureFrame.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  await act(async () => {
    void state.start();
  });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(9000);
  });
  expect(mockCapture.captureFrame).toHaveBeenCalledTimes(1);
  await act(async () => {
    release({captured: true});
  });
  expect(captured).toHaveBeenCalledTimes(1);
  await act(async () => {
    await jest.advanceTimersByTimeAsync(3000);
  });
  expect(mockCapture.captureFrame).toHaveBeenCalledTimes(2);
  await act(async () => {
    await state.stop();
    await jest.advanceTimersByTimeAsync(9000);
  });
  expect(mockCapture.captureFrame).toHaveBeenCalledTimes(2);
  expect(state.capturing).toBe(false);
});

test.each(['denied', 'restartRequired', 'unsupported'])(
  'permission %s never begins capture',
  async permission => {
    mockCapture.requestCapturePermission.mockResolvedValue(permission);
    await render();
    await act(async () => {
      await state.start();
    });
    expect(mockCapture.startCapture).not.toHaveBeenCalled();
    expect(state.error).not.toBeNull();
  },
);

test('account retirement while requesting permission prevents late start', async () => {
  let release!: (value: string) => void;
  mockCapture.requestCapturePermission.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  await render();
  await act(async () => {
    void state.start();
  });
  await act(async () => {
    renderer.update(<Harness enabled={false} />);
  });
  await act(async () => {
    release('granted');
  });
  expect(mockCapture.startCapture).not.toHaveBeenCalled();
  expect(state.capturing).toBe(false);
});

test('stop and unmount fence late capture results', async () => {
  let release!: (value: {captured: boolean}) => void;
  mockCapture.captureFrame.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  await render();
  await act(async () => {
    void state.start();
  });
  await act(async () => renderer.unmount());
  await act(async () => {
    release({captured: true});
    await jest.advanceTimersByTimeAsync(9000);
  });
  expect(captured).not.toHaveBeenCalled();
  expect(mockCapture.stopCapture).toHaveBeenCalled();
});

test('native storage failure stops future capture and reports only fixed copy', async () => {
  mockCapture.captureFrame.mockRejectedValueOnce({
    code: 'OMI_CAPTURE_QUOTA',
    message: 'private filesystem path',
  });
  await render();
  await act(async () => {
    void state.start();
  });
  expect(state.error).toContain('1 GB');
  expect(state.error).not.toContain('private');
  expect(state.capturing).toBe(false);
  expect(mockCapture.stopCapture).toHaveBeenCalled();
});

test('stop transport failure is handled without rejecting UI action', async () => {
  mockCapture.stopCapture.mockRejectedValueOnce(
    new Error('native stopped acknowledgement lost'),
  );
  await render();
  await act(async () => {
    await state.stop();
  });
  expect(state.error).toContain('Could not confirm capture stopped');
});
