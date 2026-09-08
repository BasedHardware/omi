import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Image, NativeModules, Switch, Text} from 'react-native';
import {clockLabel} from '../desktopReadClient';

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
  NativeModules.OmiRewind = mockRewind;
  mockRewind.listFrames
    .mockReset()
    .mockResolvedValue({frames: [frame('one')], nextCursor: null});
  mockRewind.readFrame.mockReset().mockImplementation(async id => image(id));
});
afterEach(() => {
  act(() => mounted.splice(0).forEach(view => view.unmount()));
});

test('loads native history, advances its cursor and opens the chosen stored frame', async () => {
  const first = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: string | null;
  }>();
  mockRewind.listFrames.mockReturnValueOnce(first.promise);
  const view = await render();
  expect(content(view)).toContain('Loading screen history…');
  expect(content(view)).not.toContain('No captures saved yet.');
  expect(mockRewind.listFrames).toHaveBeenCalledWith({
    source: 'shipping',
    query: '',
    cursor: null,
    limit: 50,
  });
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'View capture one',
    ),
  ).toHaveLength(0);
  await act(async () =>
    first.resolve({frames: [frame('one')], nextCursor: 'page-two'}),
  );
  expect(content(view)).toContain('Load more history');
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('two')],
    nextCursor: null,
  });
  await press(view, 'Load more history');
  expect(mockRewind.listFrames).toHaveBeenLastCalledWith({
    source: 'shipping',
    query: '',
    cursor: 'page-two',
    limit: 50,
  });
  expect(label(view, 'View capture one')).toBeDefined();
  await press(view, 'View capture two');
  expect(mockRewind.readFrame).toHaveBeenCalledWith('two');
  expect(
    view.root.findAllByType(Image).map(node => node.props.source.uri),
  ).toContain('data:image/jpeg;base64,image-two');
});

test('new search retires a delayed previous list response', async () => {
  const old = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: null;
  }>();
  mockRewind.listFrames.mockReturnValueOnce(old.promise);
  const view = await render();
  await act(async () =>
    label(view, 'Search screen history').props.onChangeText('current'),
  );
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('current')],
    nextCursor: null,
  });
  await press(view, 'Search history');
  await act(async () =>
    old.resolve({frames: [frame('retired')], nextCursor: null}),
  );
  expect(label(view, 'View capture current')).toBeDefined();
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'View capture retired',
    ),
  ).toHaveLength(0);
});

test('a late image cannot replace a newer selected image', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('one'), frame('two')],
    nextCursor: null,
  });
  const old = deferred<ReturnType<typeof image>>();
  mockRewind.readFrame.mockReturnValueOnce(old.promise);
  const view = await render();
  await press(view, 'View capture one');
  await press(view, 'View capture two');
  await act(async () => old.resolve(image('one')));
  const sources = view.root
    .findAllByType(Image)
    .map(node => node.props.source.uri);
  expect(sources).toContain('data:image/jpeg;base64,image-two');
  expect(sources).not.toContain('data:image/jpeg;base64,image-one');
});

test.each([
  [
    {code: 'OMI_REWIND_UNAVAILABLE'},
    'No local Rewind history is available for this account on this Mac.',
  ],
  [{code: 'OMI_REWIND_AUTH'}, 'Sign in again to open your screen history.'],
  [
    new Error('private filesystem path'),
    'Screen history could not be loaded. Try again.',
  ],
])(
  'list failure remains explicit and never claims an empty history',
  async (failure, message) => {
    mockRewind.listFrames.mockRejectedValueOnce(failure);
    const view = await render();
    expect(content(view)).toContain(message);
    expect(content(view)).not.toContain('No captures saved yet.');
    expect(content(view)).not.toContain('private filesystem path');
    mockRewind.listFrames.mockResolvedValueOnce({
      frames: [frame('recovered')],
      nextCursor: null,
    });
    await press(view, 'Refresh history');
    expect(label(view, 'View capture recovered')).toBeDefined();
  },
);

test('missing native bridge reports unavailable instead of empty success', async () => {
  delete NativeModules.OmiRewind;
  const view = await render();
  expect(content(view)).toContain(
    'No local Rewind history is available for this account on this Mac.',
  );
  expect(content(view)).not.toContain('No captures saved yet.');
});

test('a complete empty history may claim nothing is saved', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [],
    nextCursor: null,
  });
  const view = await render();
  expect(content(view)).toContain('No captures saved yet.');
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Load more history',
    ),
  ).toHaveLength(0);
});

test('Rewind capture time uses the same clock as conversations and not 1970', async () => {
  const older = new Date(2025, 7, 10, 12, 0);
  const expected = clockLabel(older.getTime(), Date.now());
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [{...frame('one'), capturedAtMs: older.getTime()}],
    nextCursor: null,
  });
  const view = await render();
  expect(content(view)).toContain(expected);
  expect(content(view)).not.toContain('1970');
});

test('a zero Rewind capture timestamp says Time unavailable instead of 1970', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [{...frame('one'), capturedAtMs: 0}],
    nextCursor: null,
  });
  const view = await render();
  expect(content(view)).toContain('Time unavailable');
  expect(content(view)).not.toContain('1970');
});

test('empty Rewind app and window names stay visible without a blank row', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [
      {
        ...frame('one'),
        appName: '',
        windowTitle: '',
      },
      {
        ...frame('two'),
        appName: ' \t\n',
        windowTitle: '\u00A0',
      },
      {
        ...frame('three'),
        appName: '  Preview app  ',
        windowTitle: '  Window three  ',
      },
    ],
    nextCursor: null,
  });
  const view = await render();
  const output = content(view);
  expect(output).toContain('Captured screen');
  expect(output).toContain('Preview app');
  expect(output).toContain('Window three');
  expect(output).not.toContain(' \t\n');
  await press(view, 'View capture one');
  expect(view.root.findByType(Image).props.accessibilityLabel).toBe(
    'Captured screen from Captured screen',
  );
  await press(view, 'View capture three');
  expect(view.root.findByType(Image).props.accessibilityLabel).toBe(
    'Captured screen from Preview app',
  );
});

test('later-page Rewind unavailability keeps frames and omits Load more', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('one')],
    nextCursor: 'page-two',
  });
  const view = await render();
  expect(label(view, 'Load more history')).toBeDefined();
  mockRewind.listFrames.mockRejectedValueOnce({code: 'OMI_REWIND_UNAVAILABLE'});
  await press(view, 'Load more history');
  expect(content(view)).toContain(
    'No local Rewind history is available for this account on this Mac.',
  );
  expect(content(view)).not.toContain('Screen history could not be loaded.');
  expect(label(view, 'View capture one')).toBeDefined();
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Load more history',
    ),
  ).toHaveLength(0);
});

test('later-page Rewind auth failures keep frames and omit Load more', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('one')],
    nextCursor: 'page-two',
  });
  const view = await render();
  mockRewind.listFrames.mockRejectedValueOnce({code: 'OMI_REWIND_AUTH'});
  await press(view, 'Load more history');
  expect(content(view)).toContain('Sign in again to open your screen history.');
  expect(label(view, 'View capture one')).toBeDefined();
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Load more history',
    ),
  ).toHaveLength(0);
});

test('generic later-page Rewind failures still offer Load more', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('one')],
    nextCursor: 'page-two',
  });
  const view = await render();
  mockRewind.listFrames.mockRejectedValueOnce(
    new Error('private filesystem path'),
  );
  await press(view, 'Load more history');
  expect(content(view)).toContain(
    'Screen history could not be loaded. Try again.',
  );
  expect(content(view)).not.toContain('private filesystem path');
  expect(label(view, 'View capture one')).toBeDefined();
  expect(label(view, 'Load more history')).toBeDefined();
});

test('later-page Rewind unavailability does not claim an empty history', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [],
    nextCursor: 'page-two',
  });
  const view = await render();
  mockRewind.listFrames.mockRejectedValueOnce({code: 'OMI_REWIND_UNAVAILABLE'});
  await press(view, 'Load more history');
  expect(content(view)).toContain(
    'No local Rewind history is available for this account on this Mac.',
  );
  expect(content(view)).not.toContain('No captures saved yet.');
  expect(content(view)).not.toContain('No captures match this search.');
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Load more history',
    ),
  ).toHaveLength(0);
});

test('an incomplete empty history does not claim nothing is saved', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [],
    nextCursor: 'page-two',
  });
  const view = await render();
  expect(content(view)).not.toContain('No captures saved yet.');
  expect(content(view)).not.toContain('No captures match this search.');
  expect(label(view, 'Load more history')).toBeDefined();
});

test('an incomplete empty search does not claim a complete miss', async () => {
  mockRewind.listFrames
    .mockResolvedValueOnce({
      frames: [frame('one')],
      nextCursor: null,
    })
    .mockResolvedValueOnce({
      frames: [],
      nextCursor: 'page-two',
    });
  const view = await render();
  await act(async () =>
    label(view, 'Search screen history').props.onChangeText('zzz'),
  );
  await press(view, 'Search history');
  expect(content(view)).not.toContain('No captures match this search.');
  expect(content(view)).not.toContain('No captures saved yet.');
  expect(label(view, 'Load more history')).toBeDefined();
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
    await press(view, 'View capture one');
    expect(content(view)).toContain('This captured frame could not be opened.');
    expect(content(view)).not.toContain('private path');
    expect(view.root.findAllByType(Image)).toHaveLength(0);
  },
);

test('late page failure and image failure cannot replace a new search', async () => {
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('one')],
    nextCursor: 'old-page',
  });
  const oldPage = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: null;
  }>();
  const oldImage = deferred<ReturnType<typeof image>>();
  mockRewind.readFrame.mockReturnValueOnce(oldImage.promise);
  const view = await render();
  await press(view, 'View capture one');
  mockRewind.listFrames.mockReturnValueOnce(oldPage.promise);
  await press(view, 'Load more history');
  await act(async () =>
    label(view, 'Search screen history').props.onChangeText('new'),
  );
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('new')],
    nextCursor: null,
  });
  await press(view, 'Search history');
  await act(async () => {
    oldPage.reject(new Error('old list'));
    oldImage.reject(new Error('old image'));
  });
  expect(label(view, 'View capture new')).toBeDefined();
  expect(content(view)).not.toContain('could not be');
  expect(content(view)).toContain('Select a capture to view it.');
});

test('image decoder failure is visible without exposing stored image data', async () => {
  const view = await render();
  await press(view, 'View capture one');
  await act(async () =>
    view.root
      .findByType(Image)
      .props.onError({nativeEvent: {error: 'private image bytes'}}),
  );
  expect(content(view)).toContain('This captured frame could not be opened.');
  expect(content(view)).not.toContain('private image bytes');
  expect(view.root.findAllByType(Image)).toHaveLength(0);
});

test('switching history source retires a delayed old-source page', async () => {
  const old = deferred<{
    frames: ReturnType<typeof frame>[];
    nextCursor: null;
  }>();
  mockRewind.listFrames.mockReturnValueOnce(old.promise);
  const view = await render();
  mockRewind.listFrames.mockResolvedValueOnce({
    frames: [frame('captured')],
    nextCursor: null,
  });
  const sourceButton = view.root.findAll(
    node =>
      node.props.accessibilityRole === 'button' &&
      node.findAllByType(Text).some(text => text.props.children === 'This app'),
  )[0]!;
  await act(async () => sourceButton.props.onPress());
  expect(mockRewind.listFrames).toHaveBeenLastCalledWith({
    source: 'captured',
    query: '',
    cursor: null,
    limit: 50,
  });
  await act(async () =>
    old.resolve({frames: [frame('shipping-stale')], nextCursor: null}),
  );
  expect(label(view, 'View capture captured')).toBeDefined();
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'View capture shipping-stale',
    ),
  ).toHaveLength(0);
});

test('unavailable capture omits Start instead of keeping a disabled Start control', async () => {
  const capture = {
    available: false,
    capturing: false,
    busy: false,
    error: null,
    start: jest.fn(async () => undefined),
    stop: jest.fn(async () => undefined),
  };
  const view = await render({capture});
  expect(content(view)).toContain(
    'Capture is available in the native Mac app.',
  );
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Start screen capture',
    ),
  ).toHaveLength(0);
  expect(content(view)).not.toContain('Start capture');
  expect(content(view)).not.toContain('Stop capture');
});

test('explicit capture controls switch source and new capture hints preserve the selected image until refresh', async () => {
  const capture = {
    available: true,
    capturing: false,
    busy: false,
    error: null,
    start: jest.fn(async () => undefined),
    stop: jest.fn(async () => undefined),
  };
  const view = await render({capture, captureRevision: 0});
  await press(view, 'Start screen capture');
  expect(capture.start).toHaveBeenCalledTimes(1);
  expect(mockRewind.listFrames).toHaveBeenLastCalledWith({
    source: 'captured',
    query: '',
    cursor: null,
    limit: 50,
  });
  await act(async () =>
    view.update(
      <DesktopRewind
        capture={{...capture, capturing: true}}
        captureRevision={0}
      />,
    ),
  );
  await press(view, 'Stop screen capture');
  expect(capture.stop).toHaveBeenCalledTimes(1);
  await press(view, 'View capture one');
  const count = mockRewind.listFrames.mock.calls.length;
  await act(async () =>
    view.update(<DesktopRewind capture={capture} captureRevision={1} />),
  );
  expect(content(view)).toContain(
    'New captures are saved. Refresh to view them.',
  );
  expect(view.root.findByType(Image).props.source.uri).toBe(
    'data:image/jpeg;base64,image-one',
  );
  expect(mockRewind.listFrames).toHaveBeenCalledTimes(count);
  await press(view, 'Refresh history');
  expect(mockRewind.listFrames).toHaveBeenCalledTimes(count + 1);
  expect(content(view)).not.toContain('New captures are saved.');
  expect(view.root.findAllByType(Image)).toHaveLength(0);
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
