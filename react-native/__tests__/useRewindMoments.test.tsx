import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';
import {NativeModules, Platform} from 'react-native';
import type {RewindMomentRecord} from '../src/rewindMomentsClient';

const mockRequest = jest.fn();
let mockInvalidate: () => void;
jest.mock('../src/omiNative', () => ({
  omiBackend: {
    request: (...args: unknown[]) => mockRequest(...args),
  },
  subscribeOmiBackendSessionInvalidated: (listener: () => void) => {
    mockInvalidate = listener;
    return () => {};
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
beforeEach(() => {
  mockRequest.mockReset();
  Platform.OS = 'ios';
  delete NativeModules.OmiRewind;
  jest.useFakeTimers();
});
afterEach(async () => {
  await act(async () => renderer?.unmount());
  jest.useRealTimers();
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

const moment = (id: number): RewindMomentRecord => ({
  frameId: `captured:owner-a:${id}`,
  capturedAtMs: 1000 - id,
  appName: 'Notes',
  windowTitle: `Note ${id}`,
  source: 'captured',
  ocrPreview: '',
});
const page = (
  items: RewindMomentRecord[],
  nextCursor: string | null = null,
) => ({
  status: 200,
  body: JSON.stringify({
    items,
    window: {hasMore: nextCursor !== null, nextCursor},
  }),
});

test('remote pagination appends, fences concurrent loads, and survives automatic refresh', async () => {
  let resolvePage!: (response: ReturnType<typeof page>) => void;
  mockRequest
    .mockResolvedValueOnce(page([moment(1)], 'older/+'))
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolvePage = resolve;
        }),
    )
    .mockResolvedValue(page([moment(3)]));
  await act(async () => {
    renderer = TestRenderer.create(<Harness />);
  });
  expect(state.hasMore).toBe(true);
  await act(async () => {
    state.loadMore();
    state.loadMore();
  });
  expect(state.loadingMore).toBe(true);
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(mockRequest).toHaveBeenCalledTimes(2);
  expect(mockRequest.mock.calls[1][0].path).toBe(
    '/v1/rewind-moments?limit=50&cursor=older%2F%2B',
  );
  await act(async () => {
    resolvePage(page([moment(2)]));
  });
  expect(state.items.map((item: {id: string}) => item.id)).toEqual([
    'captured:owner-a:1',
    'captured:owner-a:2',
  ]);
  expect(state.hasMore).toBe(false);
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(mockRequest).toHaveBeenCalledTimes(2);
  await act(async () => {
    state.refresh();
  });
  expect(state.items.map((item: {id: string}) => item.id)).toEqual([
    'captured:owner-a:3',
  ]);
});

test('local history can page past 50 and acknowledged metadata is not uploaded on every poll', async () => {
  Platform.OS = 'macos';
  const frames = Array.from({length: 51}, (_, index) => {
    const record = moment(index + 1);
    return {
      id: record.frameId,
      capturedAtMs: record.capturedAtMs,
      appName: record.appName,
      windowTitle: record.windowTitle,
    };
  });
  NativeModules.OmiRewind = {
    listFrames: jest.fn(async ({source, cursor}) => ({
      frames:
        source === 'shipping'
          ? []
          : cursor === null
          ? frames.slice(0, 50)
          : frames.slice(50),
      nextCursor:
        source === 'shipping' || cursor !== null ? null : 'local-older',
    })),
  };
  mockRequest.mockImplementation(async request =>
    request.method === 'POST'
      ? {status: 201, body: JSON.stringify({moment: JSON.parse(request.body)})}
      : page([]),
  );
  await act(async () => {
    renderer = TestRenderer.create(<Harness />);
  });
  expect(state.items).toHaveLength(50);
  expect(state.hasMore).toBe(true);
  expect(state.sync).toBe('saved');
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(
    mockRequest.mock.calls.filter(call => call[0].method === 'POST'),
  ).toHaveLength(50);
  await act(async () => {
    state.loadMore();
  });
  expect(state.items).toHaveLength(51);
  expect(state.items[50].id).toBe('captured:owner-a:51');
  expect(state.hasMore).toBe(false);
  expect(
    mockRequest.mock.calls.filter(call => call[0].method === 'POST'),
  ).toHaveLength(51);
});

test('session invalidation during a delayed read clears local frames and prevents stale uploads', async () => {
  Platform.OS = 'macos';
  NativeModules.OmiRewind = {
    listFrames: jest.fn(async ({source}) => ({
      frames:
        source === 'shipping'
          ? []
          : [
              {
                id: moment(1).frameId,
                capturedAtMs: 999,
                appName: 'Notes',
                windowTitle: 'Private A',
              },
            ],
      nextCursor: null,
    })),
  };
  let finishRead!: (response: ReturnType<typeof page>) => void;
  mockRequest.mockImplementation(
    () =>
      new Promise(resolve => {
        finishRead = resolve;
      }),
  );
  await act(async () => {
    renderer = TestRenderer.create(<Harness />);
  });
  await act(async () => {
    mockInvalidate();
    finishRead(page([moment(2)]));
  });
  expect(state.items).toEqual([]);
  expect(state.sync).toBe('idle');
  await act(async () => {
    state.refresh();
    state.loadMore();
    jest.advanceTimersByTime(30000);
  });
  expect(mockRequest).toHaveBeenCalledTimes(1);
  mockRequest.mockResolvedValue(page([]));
  await act(async () => {
    renderer.update(<Harness enabled={false} />);
  });
  // A late sign-out event while disabled must not block the next sign-in.
  await act(async () => {
    mockInvalidate();
  });
  Platform.OS = 'ios';
  await act(async () => {
    renderer.update(<Harness />);
  });
  expect(mockRequest).toHaveBeenCalledTimes(2);
  expect(state.status).toBe('ready');
});
