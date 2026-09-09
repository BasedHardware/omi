import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  AppState,
  FlatList,
  Image,
  NativeModules,
  Switch,
  Text,
  TextInput,
} from 'react-native';

const mockRewind = {listFrames: jest.fn(), readFrame: jest.fn()};
NativeModules.OmiRewind = mockRewind;
const {DesktopRewind} = require('./DesktopRewind');

const frame = (id: string) => ({
  id,
  capturedAtMs: 1788739200000,
  appName: 'Preview app',
  windowTitle: `Window ${id}`,
});
const image = (id: string) => ({
  id,
  mimeType: 'image/jpeg',
  base64: `image-${id}`,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return {promise, resolve, reject};
}
const mounted: ReactTestRenderer.ReactTestRenderer[] = [];
async function render(props: Record<string, unknown> = {}) {
  let result!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    result = ReactTestRenderer.create(<DesktopRewind {...props} />);
  });
  mounted.push(result);
  return result;
}
function label(view: ReactTestRenderer.ReactTestRenderer, name: string) {
  return view.root.findAll(node => node.props.accessibilityLabel === name)[0]!;
}
function content(view: ReactTestRenderer.ReactTestRenderer) {
  return view.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
}
async function press(view: ReactTestRenderer.ReactTestRenderer, name: string) {
  await act(async () => {
    label(view, name).props.onPress();
  });
}
beforeEach(() => {
  jest.useFakeTimers();
  AppState.currentState = 'active';
  jest.mocked(AppState.addEventListener).mockReturnValue({remove: jest.fn()});
  NativeModules.OmiRewind = mockRewind;
  mockRewind.listFrames.mockReset().mockImplementation(async ({source}) => ({
    frames: source === 'captured' ? [frame('captured:one')] : [],
    nextCursor: null,
  }));
  mockRewind.readFrame.mockReset().mockImplementation(async id => image(id));
});
afterEach(() => {
  act(() => mounted.splice(0).forEach(view => view.unmount()));
  jest.useRealTimers();
});

function rows(view: ReactTestRenderer.ReactTestRenderer) {
  return view.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .filter(value => typeof value === 'string' && value.startsWith('Window '));
}
const firstPage = () =>
  Array.from({length: 50}, (_, index) => ({
    ...frame(`captured:${index}`),
    capturedAtMs: 1000 - index,
  }));

test('merges native history, advances the source cursor and opens the stored frame', async () => {
  const first = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: string | null;
  }>();
  mockRewind.listFrames.mockImplementation(({source, cursor}) => {
    if (source === 'shipping') {
      return Promise.resolve({
        frames: [{...frame('shipping:old'), capturedAtMs: 0}],
        nextCursor: null,
      });
    }
    return cursor
      ? Promise.resolve({
          frames: [{...frame('captured:two'), capturedAtMs: 1}],
          nextCursor: null,
        })
      : first.promise;
  });
  const view = await render();
  expect(content(view)).toContain('Loading screen history…');
  expect(content(view)).not.toContain('No captures saved yet.');
  for (const source of ['captured', 'shipping']) {
    expect(mockRewind.listFrames).toHaveBeenCalledWith({
      source,
      query: '',
      cursor: null,
      limit: 50,
    });
  }
  await act(async () =>
    first.resolve({frames: firstPage(), nextCursor: 'page-two'}),
  );
  expect(view.root.findByType(FlatList).props.data).toHaveLength(50);
  expect(rows(view).length).toBeLessThan(50);
  await press(view, 'Load more history');
  expect(mockRewind.listFrames).toHaveBeenCalledWith({
    source: 'captured',
    query: '',
    cursor: 'page-two',
    limit: 50,
  });
  expect(
    view.root
      .findByType(FlatList)
      .props.data.slice(-2)
      .map((item: ReturnType<typeof frame>) => item.windowTitle),
  ).toEqual(['Window captured:two', 'Window shipping:old']);
  await press(view, 'View capture captured:0');
  expect(mockRewind.readFrame).toHaveBeenCalledWith('captured:0');
  expect(view.root.findByType(Image).props.source.uri).toBe(
    'data:image/jpeg;base64,image-captured:0',
  );
});

test('uses the external query for both stores without duplicate input or source switches', async () => {
  mockRewind.listFrames.mockImplementation(async ({source}) => ({
    frames: [
      {
        ...frame(`${source}:one`),
        capturedAtMs: source === 'shipping' ? 20 : 10,
      },
    ],
    nextCursor: null,
  }));
  const view = await render({query: 'meeting'});
  expect(view.root.findAllByType(TextInput)).toHaveLength(0);
  expect(content(view)).not.toContain('Existing Omi history');
  expect(content(view)).not.toContain('This app');
  for (const source of ['captured', 'shipping']) {
    expect(mockRewind.listFrames).toHaveBeenCalledWith({
      source,
      query: 'meeting',
      cursor: null,
      limit: 50,
    });
  }
  expect(rows(view)).toEqual(['Window shipping:one', 'Window captured:one']);
});

test('a changed query retires delayed responses from both old stores', async () => {
  const old = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: null;
  }>();
  mockRewind.listFrames.mockImplementation(async ({source, query}) =>
    query === ''
      ? old.promise
      : {frames: [frame(`${source}:current`)], nextCursor: null},
  );
  const view = await render();
  await act(async () => view.update(<DesktopRewind query="current" />));
  await act(async () =>
    old.resolve({frames: [frame('retired')], nextCursor: null}),
  );
  expect(rows(view)).toEqual([
    'Window captured:current',
    'Window shipping:current',
  ]);
});

test('a late image cannot replace a newer selected image', async () => {
  mockRewind.listFrames.mockImplementation(async ({source}) => ({
    frames:
      source === 'captured'
        ? [frame('captured:one'), frame('captured:two')]
        : [],
    nextCursor: null,
  }));
  const old = deferred<ReturnType<typeof image>>();
  mockRewind.readFrame.mockReturnValueOnce(old.promise);
  const view = await render();
  await press(view, 'View capture captured:one');
  await press(view, 'View capture captured:two');
  await act(async () => old.resolve(image('captured:one')));
  expect(view.root.findByType(Image).props.source.uri).toBe(
    'data:image/jpeg;base64,image-captured:two',
  );
});

test.each([
  [
    {code: 'OMI_REWIND_AUTH'},
    'Sign in again from Settings to open your screen history.',
  ],
  [new Error('private filesystem path'), 'Screen history could not be loaded.'],
])(
  'list failure remains explicit and refresh recovers',
  async (failure, message) => {
    mockRewind.listFrames.mockRejectedValue(failure);
    const view = await render();
    expect(content(view)).toContain(message);
    expect(content(view)).not.toContain('No captures saved yet.');
    expect(content(view)).not.toContain('private filesystem path');
    mockRewind.listFrames.mockImplementation(async ({source}) => ({
      frames: source === 'captured' ? [frame('captured:recovered')] : [],
      nextCursor: null,
    }));
    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    expect(label(view, 'View capture captured:recovered')).toBeDefined();
  },
);

test('an absent store is tolerated while other failures visibly mark partial history', async () => {
  mockRewind.listFrames.mockImplementation(async ({source}) => {
    if (source === 'shipping') {
      throw {code: 'OMI_REWIND_UNAVAILABLE'};
    }
    return {frames: [frame('captured:one')], nextCursor: null};
  });
  const view = await render();
  expect(label(view, 'View capture captured:one')).toBeDefined();
  expect(content(view)).not.toContain('could not be loaded');
  mockRewind.listFrames.mockImplementation(async ({source}) => {
    if (source === 'shipping') {
      throw new Error('private path');
    }
    return {frames: [frame('captured:one')], nextCursor: null};
  });
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(label(view, 'View capture captured:one')).toBeDefined();
  expect(content(view)).toContain('Some screen history could not be loaded.');
  expect(content(view)).not.toContain('private path');
});

test('both missing stores are empty, but a missing native bridge remains unavailable', async () => {
  mockRewind.listFrames.mockRejectedValue({code: 'OMI_REWIND_UNAVAILABLE'});
  const empty = await render();
  expect(content(empty)).toContain('No captures saved yet.');
  delete NativeModules.OmiRewind;
  const unavailable = await render();
  expect(content(unavailable)).toContain(
    'No local Recall history is available for this account on this Mac.',
  );
  expect(content(unavailable)).not.toContain('No captures saved yet.');
});

test.each(['rejected', 'wrong-id'])(
  'image %s cannot display unrelated bytes',
  async mode => {
    if (mode === 'rejected') {
      mockRewind.readFrame.mockRejectedValueOnce(new Error('private path'));
    } else {
      mockRewind.readFrame.mockResolvedValueOnce(image('another'));
    }
    const view = await render();
    await press(view, 'View capture captured:one');
    expect(content(view)).toContain('This captured frame could not be opened.');
    expect(content(view)).not.toContain('private path');
    expect(view.root.findAllByType(Image)).toHaveLength(0);
  },
);

test('late page and image failures cannot replace a new query', async () => {
  const oldPage = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: null;
  }>();
  const oldImage = deferred<ReturnType<typeof image>>();
  mockRewind.listFrames.mockImplementation(async ({source, cursor, query}) => {
    if (source === 'shipping') {
      return {frames: [], nextCursor: null};
    }
    if (query === 'new') {
      return {frames: [frame('captured:new')], nextCursor: null};
    }
    if (cursor) {
      return oldPage.promise;
    }
    return {frames: firstPage(), nextCursor: 'old-page'};
  });
  mockRewind.readFrame.mockReturnValueOnce(oldImage.promise);
  const view = await render();
  await press(view, 'View capture captured:0');
  await press(view, 'Load more history');
  await act(async () => view.update(<DesktopRewind query="new" />));
  await act(async () => {
    oldPage.reject(new Error('old list'));
    oldImage.reject(new Error('old image'));
  });
  expect(rows(view)).toEqual(['Window captured:new']);
  expect(content(view)).not.toContain('could not be');
  expect(content(view)).toContain('Select a capture to view it.');
});

test('image decoder failure is visible without exposing stored image data', async () => {
  const view = await render();
  await press(view, 'View capture captured:one');
  await act(async () =>
    view.root
      .findByType(Image)
      .props.onError({nativeEvent: {error: 'private image bytes'}}),
  );
  expect(content(view)).toContain('This captured frame could not be opened.');
  expect(content(view)).not.toContain('private image bytes');
  expect(view.root.findAllByType(Image)).toHaveLength(0);
});

test('new captures and periodic refresh update Recall without reopening the selected image', async () => {
  const view = await render({captureRevision: 0});
  await press(view, 'View capture captured:one');
  const count = mockRewind.listFrames.mock.calls.length;
  mockRewind.listFrames.mockImplementation(async ({source}) => ({
    frames:
      source === 'captured'
        ? [frame('captured:new'), frame('captured:one')]
        : [],
    nextCursor: null,
  }));
  await act(async () => view.update(<DesktopRewind captureRevision={1} />));
  expect(rows(view)).toContain('Window captured:new');
  expect(view.root.findByType(Image).props.source.uri).toBe(
    'data:image/jpeg;base64,image-captured:one',
  );
  expect(mockRewind.listFrames).toHaveBeenCalledTimes(count + 2);
  expect(mockRewind.readFrame).toHaveBeenCalledTimes(1);
  expect(label(view, 'Refresh history')).toBeUndefined();
  expect(label(view, 'Start screen capture')).toBeUndefined();
  expect(content(view)).not.toContain('Timeline');
  await act(async () => {
    jest.advanceTimersByTime(15000);
  });
  expect(mockRewind.listFrames).toHaveBeenCalledTimes(count + 4);
  act(() => view.unmount());
  mounted.splice(mounted.indexOf(view), 1);
  await act(async () => {
    jest.advanceTimersByTime(30000);
  });
  expect(mockRewind.listFrames).toHaveBeenCalledTimes(count + 4);
});

test('background pauses refresh and foreground refreshes without waiting for the timer', async () => {
  let change!: (state: 'active' | 'background') => void;
  const remove = jest.fn();
  const subscription = jest
    .spyOn(AppState, 'addEventListener')
    .mockImplementation((_event, listener) => {
      change = listener;
      return {remove};
    });
  try {
    const view = await render();
    mockRewind.listFrames.mockClear();
    act(() => change('background'));
    await act(async () => {
      jest.advanceTimersByTime(30000);
    });
    expect(mockRewind.listFrames).not.toHaveBeenCalled();
    await act(async () => change('active'));
    expect(mockRewind.listFrames).toHaveBeenCalledTimes(2);
    act(() => view.unmount());
    mounted.splice(mounted.indexOf(view), 1);
    expect(remove).toHaveBeenCalledTimes(1);
  } finally {
    subscription.mockRestore();
  }
});

test('automatic refresh never replaces older pages the user has loaded', async () => {
  mockRewind.listFrames.mockImplementation(async ({source, cursor}) =>
    source === 'shipping'
      ? {frames: [], nextCursor: null}
      : cursor
      ? {frames: [frame('captured:older')], nextCursor: null}
      : {frames: firstPage(), nextCursor: 'older'},
  );
  const view = await render({captureRevision: 0});
  await press(view, 'Load more history');
  expect(view.root.findByType(FlatList).props.data).toEqual(
    expect.arrayContaining([frame('captured:older')]),
  );
  mockRewind.listFrames.mockClear();
  await act(async () => view.update(<DesktopRewind captureRevision={1} />));
  await act(async () => {
    jest.advanceTimersByTime(30000);
  });
  expect(mockRewind.listFrames).not.toHaveBeenCalled();
  expect(view.root.findByType(FlatList).props.data).toEqual(
    expect.arrayContaining([frame('captured:older')]),
  );
});

test('Settings Screen Capture switch operates the shared producer instead of changing a staged preference', async () => {
  const {DesktopSettings} = require('./DesktopSettings');
  const previous = NativeModules.OmiDesktopCommands;
  const setDesktopPreference = jest.fn(async () => ({}));
  NativeModules.OmiDesktopCommands = {
    loadDesktopPreferences: jest.fn(async () => ({screenCapture: false})),
    permissionStatus: jest.fn(async () => ({
      screen: 'unknown',
      microphone: 'unknown',
      notifications: 'unknown',
    })),
    setDesktopPreference,
  };
  const capture = {
    available: true,
    capturing: true,
    busy: false,
    error: null,
    start: jest.fn(async () => undefined),
    stop: jest.fn(async () => undefined),
  };
  const props = {
    session: 'signed-out',
    signingIn: false,
    softwarePlaneLocked: false,
    onSignIn: () => undefined,
    onSignOut: () => undefined,
  };
  let view!: ReactTestRenderer.ReactTestRenderer;
  try {
    await act(async () => {
      view = ReactTestRenderer.create(
        <DesktopSettings {...props} capture={capture} />,
      );
    });
    expect(view.root.findAllByType(Switch)[0]!.props.value).toBe(true);
    await act(async () =>
      view.root.findAllByType(Switch)[0]!.props.onValueChange(false),
    );
    expect(capture.stop).toHaveBeenCalledTimes(1);
    await act(async () =>
      view.update(
        <DesktopSettings {...props} capture={{...capture, capturing: false}} />,
      ),
    );
    expect(view.root.findAllByType(Switch)[0]!.props.value).toBe(false);
    await act(async () =>
      view.root.findAllByType(Switch)[0]!.props.onValueChange(true),
    );
    expect(capture.start).toHaveBeenCalledTimes(1);
    expect(setDesktopPreference).not.toHaveBeenCalled();
  } finally {
    if (view !== undefined) {
      await act(async () => view.unmount());
    }
    NativeModules.OmiDesktopCommands = previous;
  }
});

test.each(['OMI_REWIND_AUTH', 'OMI_REWIND_OWNER_CHANGED'])(
  'refresh %s clears private rows, pagination and the selected image',
  async code => {
    mockRewind.listFrames.mockImplementation(async ({source}) => ({
      frames: source === 'captured' ? firstPage() : [],
      nextCursor: source === 'captured' ? 'next' : null,
    }));
    const view = await render();
    await press(view, 'View capture captured:0');
    expect(view.root.findByType(Image)).toBeDefined();
    expect(label(view, 'Load more history')).toBeDefined();
    mockRewind.listFrames.mockRejectedValue({code});
    await act(async () => jest.advanceTimersByTime(15000));
    expect(rows(view)).toEqual([]);
    expect(view.root.findAllByType(Image)).toHaveLength(0);
    expect(
      view.root.findAll(
        node => node.props.accessibilityLabel === 'Load more history',
      ),
    ).toHaveLength(0);
    expect(content(view)).not.toContain('Select a capture to view it.');
    expect(content(view)).not.toContain('No captures saved yet.');
  },
);

test('a delayed preview cannot restore private bytes after refresh loses ownership', async () => {
  const preview = deferred<ReturnType<typeof image>>();
  mockRewind.readFrame.mockReturnValueOnce(preview.promise);
  const view = await render();
  await press(view, 'View capture captured:one');
  mockRewind.listFrames.mockRejectedValue({code: 'OMI_REWIND_OWNER_CHANGED'});
  await act(async () => jest.advanceTimersByTime(15000));
  await act(async () => preview.resolve(image('captured:one')));
  expect(rows(view)).toEqual([]);
  expect(view.root.findAllByType(Image)).toHaveLength(0);
});

test('transient refresh failure preserves readable rows and selected preview', async () => {
  const view = await render();
  await press(view, 'View capture captured:one');
  mockRewind.listFrames.mockRejectedValue(new Error('temporary'));
  await act(async () => jest.advanceTimersByTime(15000));
  expect(rows(view)).toEqual(['Window captured:one']);
  expect(view.root.findByType(Image).props.source.uri).toBe(
    'data:image/jpeg;base64,image-captured:one',
  );
  expect(content(view)).toContain('Screen history could not be loaded.');
});
