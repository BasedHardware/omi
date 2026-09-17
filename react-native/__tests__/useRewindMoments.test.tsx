import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';

const mockRequest = jest.fn();
jest.mock('../src/omiNative', () => ({
  omiBackend: {
    request: (...args: unknown[]) => mockRequest(...args),
  },
}));
jest.mock('react-native', () => ({
  AppState: {
    currentState: 'active',
    addEventListener: () => ({remove() {}}),
  },
  NativeModules: {},
  Platform: {OS: 'ios'},
}));

const {useRewindMoments} = require('../src/app/useRewindMoments');
let state: ReturnType<typeof useRewindMoments>;
function Harness({enabled = true}: {enabled?: boolean}) {
  state = useRewindMoments(enabled);
  return null;
}

let renderer: TestRenderer.ReactTestRenderer;
afterEach(async () => {
  await act(async () => renderer?.unmount());
});

test('browser and phone surfaces never invent local Recall or pretend they saved pixels', async () => {
  mockRequest.mockResolvedValue({
    id: 'rewind-moments-read',
    status: 503,
    body: JSON.stringify({
      error: {code: 'service_unavailable', retryable: true, action: 'retry'},
    }),
  });
  await act(async () => {
    renderer = TestRenderer.create(<Harness />);
  });
  expect(state.items).toEqual([]);
  expect(state.status).toBe('error');
  expect(state.sync).not.toBe('saved');
  expect(
    mockRequest.mock.calls.some(call => String(call[0]?.method) === 'POST'),
  ).toBe(false);
});
