/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import {Animated} from 'react-native';

const mockReact = React;

let mockViewportWidth = 1200;
let mockPlatformOS = 'ios';
let mockReduceMotion = false;
let mockReduceMotionListener: ((enabled: boolean) => void) | undefined;
let mockDesktopSearchListener: (() => void) | undefined;
const mockSearchFocus = jest.fn();
const mockChatScrollToEnd = jest.fn();
type MockRequest = {body?: string; id: string; method: string; path: string};
type MockResponse = {body: string | null; id: string; status: number};
const mockNative = {
  connectDevice: jest.fn(async (_deviceId: string) => undefined),
  disconnectDevice: jest.fn(async (_deviceId: string) => undefined),
  getSnapshot: jest.fn(async () => ({
    audioRoute: 'phone-mic',
    background: 'inactive',
    bluetooth: 'poweredOn',
    capture: 'idle',
    captureMode: 'stream',
    devices: [
      {battery: 82, connected: true, id: 'omi-1', name: 'Omi', rssi: -54},
    ],
    lastEvent: 'Connected to Omi',
    microphone: 'granted',
    notifications: 'granted',
  })),
  startScan: jest.fn(async (_timeoutSeconds?: number) => []),
};
const mockBackend = {
  cancelGenerationEvents: jest.fn(async (_generationId: string) => undefined),
  generationEvents: jest.fn<Promise<MockResponse>, [string, string | null]>(
    async (_generationId: string, _lastEventId: string | null) => ({
      body: null,
      id: '',
      status: 500,
    }),
  ),
  request: jest.fn<Promise<MockResponse>, [MockRequest]>(
    async (_request: MockRequest) => ({
      body: null,
      id: '',
      status: 500,
    }),
  ),
};
const mockAuth = {
  hasCompletedOnboarding: jest.fn(async () => true),
  hasCloudSession: jest.fn(async () => false),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(async () => ({signedIn: true})),
  signOut: jest.fn(async () => ({signedOut: true})),
};

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({
      children,
      ...props
    }: {
      children?: React.ReactNode;
      [key: string]: unknown;
    }) =>
      ReactRuntime.createElement(name, props, children);
  const Text = component('Text');
  const View = component('View');
  const TextInput = ReactRuntime.forwardRef(
    (props: Record<string, unknown>, ref: React.Ref<unknown>) => {
      ReactRuntime.useImperativeHandle(ref, () => ({focus: mockSearchFocus}));
      return ReactRuntime.createElement('TextInput', props);
    },
  );
  class MockAnimatedValue {
    value: number;
    interpolate = jest.fn((config: Record<string, unknown>) => ({
      config,
      type: 'interpolation',
    }));
    setValue = jest.fn((value: number) => {
      this.value = value;
    });

    constructor(value: number) {
      this.value = value;
    }
  }
  const timing = jest.fn(() => ({start: jest.fn(), stop: jest.fn()}));
  const spring = jest.fn(() => ({start: jest.fn(), stop: jest.fn()}));
  const parallel = jest.fn((animations: Array<{start: () => void}>) => ({
    start: () => animations.forEach(animation => animation.start()),
    stop: jest.fn(),
  }));
  const sequence = jest.fn((animations: Array<{start: () => void}>) => ({
    start: () => animations.forEach(animation => animation.start()),
    stop: jest.fn(),
  }));
  const stagger = jest.fn(
    (_delay: number, animations: Array<{start: () => void}>) =>
      parallel(animations),
  );
  const loop = jest.fn((animation: {start: () => void}) => ({
    start: animation.start,
    stop: jest.fn(),
  }));
  const FlatList = ({
    accessibilityLabel,
    data,
    ListEmptyComponent,
    ListFooterComponent,
    ListHeaderComponent,
    renderItem,
    style,
  }: {
    accessibilityLabel?: string;
    data: unknown[];
    ListEmptyComponent: React.ReactNode;
    ListFooterComponent: React.ReactNode;
    ListHeaderComponent: React.ReactNode;
    renderItem: (item: {item: unknown}) => React.ReactNode;
    style?: unknown;
  }) => (
    <View accessibilityLabel={accessibilityLabel} style={style}>
      {ListHeaderComponent}
      {data.map((item, index) => (
        <View key={index}>{renderItem({item})}</View>
      ))}
      {data.length === 0 && ListEmptyComponent}
      {ListFooterComponent}
    </View>
  );

  return {
    AccessibilityInfo: {
      addEventListener: jest.fn(
        (_event: string, listener: (enabled: boolean) => void) => {
          mockReduceMotionListener = listener;
          return {remove: jest.fn()};
        },
      ),
      isReduceMotionEnabled: jest.fn(() => Promise.resolve(mockReduceMotion)),
    },
    ActivityIndicator: component('ActivityIndicator'),
    Animated: {
      loop,
      parallel,
      sequence,
      spring,
      stagger,
      timing,
      Value: MockAnimatedValue,
      View: component('AnimatedView'),
    },
    Easing: {
      bezier: jest.fn((x1, y1, x2, y2) => [x1, y1, x2, y2]),
      cubic: 'cubic',
      linear: jest.fn(value => value),
      out: jest.fn(value => value),
    },
    FlatList,
    Image: component('Image'),
    KeyboardAvoidingView: component('KeyboardAvoidingView'),
    NativeEventEmitter: jest.fn(() => ({
      addListener: (_event: string, listener: () => void) => {
        mockDesktopSearchListener = listener;
        return {remove: jest.fn()};
      },
    })),
    NativeModules: {
      OmiDesktopCommands: {
        addListener: jest.fn(),
        removeListeners: jest.fn(),
      },
    },
    Platform: {
      get OS() {
        return mockPlatformOS;
      },
    },
    Pressable: component('Pressable'),
    requireNativeComponent: (name: string) => component(name),
    SafeAreaView: component('SafeAreaView'),
    ScrollView: ReactRuntime.forwardRef(
      (
        {children, ...props}: {children?: React.ReactNode},
        ref: React.Ref<unknown>,
      ) => {
        ReactRuntime.useImperativeHandle(ref, () => ({
          scrollToEnd: mockChatScrollToEnd,
        }));
        return ReactRuntime.createElement('ScrollView', props, children);
      },
    ),
    StyleSheet: {create: <T,>(styles: T) => styles},
    Text,
    TextInput,
    useWindowDimensions: () => ({
      fontScale: 1,
      height: 900,
      scale: 1,
      width: mockViewportWidth,
    }),
    View,
  };
});

jest.mock('lucide-react-native', () => {
  const ReactRuntime = require('react');
  const icon = (name: string) => (props: Record<string, unknown>) =>
    ReactRuntime.createElement(name, props);
  return {
    ArrowUp: icon('ArrowUp'),
    Brain: icon('Brain'),
    GanttChartSquare: icon('GanttChartSquare'),
    House: icon('House'),
    ListChecks: icon('ListChecks'),
    Mic: icon('Mic'),
    Paperclip: icon('Paperclip'),
  };
});

jest.mock('react-native-safe-area-context', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...props}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, props, children);
  return {
    SafeAreaProvider: component('SafeAreaProvider'),
    SafeAreaView: component('SafeAreaView'),
  };
});

jest.mock(
  'lucide-react-native/icons/arrow-up',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('ArrowUp', props),
);
jest.mock(
  'lucide-react-native/icons/brain',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Brain', props),
);
jest.mock(
  'lucide-react-native/icons/chevron-left',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('ChevronLeft', props),
);
jest.mock(
  'lucide-react-native/icons/ellipsis',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Ellipsis', props),
);
jest.mock(
  'lucide-react-native/icons/square-chart-gantt',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('GanttChartSquare', props),
);
jest.mock(
  'lucide-react-native/icons/house',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('House', props),
);
jest.mock(
  'lucide-react-native/icons/list-checks',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('ListChecks', props),
);
jest.mock(
  'lucide-react-native/icons/message-circle',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('MessageCircle', props),
);
jest.mock(
  'lucide-react-native/icons/mic',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Mic', props),
);
jest.mock(
  'lucide-react-native/icons/paperclip',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Paperclip', props),
);
jest.mock(
  'lucide-react-native/icons/panel-left',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('PanelLeft', props),
);
jest.mock(
  'lucide-react-native/icons/panel-left-close',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('PanelLeftClose', props),
);
jest.mock(
  'lucide-react-native/icons/search',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Search', props),
);
jest.mock(
  'lucide-react-native/icons/square',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Square', props),
);

jest.mock('../src/omiNative', () => ({
  browserScanErrorMessage: (error: {name?: string; reason?: string}) => {
    if (error.name !== 'BrowserScanError') {
      return null;
    }
    return {
      cancelled: 'Scan cancelled. No Omi device was discovered.',
      denied: 'Bluetooth permission was denied. No Omi device was discovered.',
      error: 'Bluetooth scanning failed. No Omi device was discovered.',
      unsupported:
        'Bluetooth scanning is not supported in this browser. No Omi device was discovered.',
    }[error.reason ?? ''];
  },
  omiBackend: {
    cancelGenerationEvents: (generationId: string) =>
      mockBackend.cancelGenerationEvents(generationId),
    generationEvents: (generationId: string, lastEventId: string | null) =>
      mockBackend.generationEvents(generationId, lastEventId),
    request: (request: MockRequest) => mockBackend.request(request),
  },
  omiAuth: {
    hasCompletedOnboarding: () => mockAuth.hasCompletedOnboarding(),
    hasCloudSession: () => mockAuth.hasCloudSession(),
    markOnboardingComplete: () => mockAuth.markOnboardingComplete(),
    signIn: () => mockAuth.signIn(),
    signOut: () => mockAuth.signOut(),
  },
  isBluetoothScanAvailable: (state: string | undefined) =>
    state === 'poweredOn' || state === 'available' || state === 'selected',
  omiNative: {
    connectDevice: (deviceId: string) => mockNative.connectDevice(deviceId),
    disconnectDevice: (deviceId: string) =>
      mockNative.disconnectDevice(deviceId),
    getSnapshot: () => mockNative.getSnapshot(),
    startScan: (timeoutSeconds?: number) =>
      mockNative.startScan(timeoutSeconds),
  },
}));

import App, {omiDotColor, resolveInitialRoute} from '../App';

function chatMessage(
  id: string,
  text: string = id,
  sender: 'human' | 'ai' = 'ai',
  generationOutcome: 'completed' | 'cancelled' | 'failed' | null = 'completed',
) {
  return {id, text, sender, createdAt: 1, generationOutcome};
}

function mockBackendResponse(request: MockRequest): MockResponse {
  if (request.path === '/v1/chat-messages?limit=50') {
    return {
      id: request.id,
      status: 200,
      body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
    };
  }
  if (request.path === '/v1/conversations?limit=50&offset=0') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify([
        {
          id: 'conversation-1',
          structured: {
            title: 'QA bridge check',
            overview: 'A deterministic conversation.',
          },
          created_at: '2026-08-07T10:00:00.000Z',
          updated_at: '2026-08-07T12:00:00.000Z',
          started_at: '2026-08-07T11:50:00.000Z',
          finished_at: '2026-08-07T12:00:00.000Z',
          source: 'omi',
          status: 'completed',
          discarded: false,
          starred: false,
          visibility: 'private',
          is_locked: false,
          folder_id: null,
        },
      ]),
    };
  }
  const tasks = request.path === '/v1/tasks';
  return {
    id: request.id,
    status: 200,
    body: JSON.stringify({
      contractVersion: '1.0.0',
      items: [],
      window: {
        status: 'complete',
        complete: true,
        hasMore: false,
        nextCursor: null,
      },
      completeness: {
        version: tasks ? 'tasks-completeness-v1' : 'recall-completeness-v1',
        status: 'complete',
        reasons: [],
      },
      absence: null,
    }),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockViewportWidth = 1200;
  mockPlatformOS = 'ios';
  mockReduceMotion = false;
  mockReduceMotionListener = undefined;
  mockDesktopSearchListener = undefined;
  mockSearchFocus.mockClear();
  mockBackend.cancelGenerationEvents.mockResolvedValue(undefined);
  mockBackend.generationEvents.mockResolvedValue({
    body: null,
    id: '',
    status: 500,
  });
  mockBackend.request.mockImplementation(async request =>
    mockBackendResponse(request),
  );
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.markOnboardingComplete.mockResolvedValue(undefined);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  mockNative.getSnapshot.mockImplementation(() => new Promise(() => {}));
  mockNative.startScan.mockResolvedValue([]);
});

test.each([
  ['cancelled', 'Scan cancelled. No Omi device was discovered.'],
  ['denied', 'Bluetooth permission was denied. No Omi device was discovered.'],
  [
    'unsupported',
    'Bluetooth scanning is not supported in this browser. No Omi device was discovered.',
  ],
  ['error', 'Bluetooth scanning failed. No Omi device was discovered.'],
])(
  'surfaces an honest browser scan outcome for %s',
  async (reason, message) => {
    mockViewportWidth = 390;
    mockNative.getSnapshot.mockResolvedValue({
      audioRoute: 'browser',
      background: 'inactive',
      bluetooth: 'poweredOn',
      capture: 'idle',
      captureMode: 'stream',
      devices: [],
      lastEvent: 'Omi device capture is not wired in the browser.',
      microphone: 'unsupported',
      notifications: 'unknown',
    });
    mockNative.startScan.mockRejectedValueOnce({
      name: 'BrowserScanError',
      reason,
    });
    const renderer = await renderApp();
    expect(mockNative.getSnapshot).toHaveBeenCalled();

    await ReactTestRenderer.act(async () => {
      const scan = renderer.root.find(
        node => node.props.accessibilityLabel === 'Scan for Omi devices',
      );
      expect(scan.props.onPress).toEqual(expect.any(Function));
      await scan.props.onPress();
    });

    expect(mockNative.startScan).toHaveBeenCalledWith(8);
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain(message);
    expect(output).not.toContain('Browser device selected');
  },
);

async function renderApp(initialRoute?: string) {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App initialRoute={initialRoute} />);
    await Promise.resolve();
    await new Promise<void>(resolve => setTimeout(resolve, 0));
  });
  return renderer!;
}

test('uses only allowlisted host-selected initial routes', () => {
  for (const route of [
    'Home',
    'Conversations',
    'Memories',
    'Tasks',
    'Connectors',
    'Settings',
  ]) {
    expect(resolveInitialRoute(route)).toBe(route);
  }
  for (const removed of ['Chat', 'Recaps', 'My Apps', 'Persona']) {
    expect(resolveInitialRoute(removed)).toBe('Home');
  }
  expect(resolveInitialRoute('Goals')).toBe('Home');
  expect(resolveInitialRoute()).toBe('Home');
});

test('derives a stable, varied Omi dot palette from a stable identity', () => {
  const omi = Array.from({length: 8}, (_, index) => omiDotColor('omi', index));
  expect(omi).toEqual(
    Array.from({length: 8}, (_, index) => omiDotColor('omi', index)),
  );
  expect(new Set(omi).size).toBeGreaterThan(1);
  expect(omi).not.toEqual(
    Array.from({length: 8}, (_, index) => omiDotColor('another-agent', index)),
  );
});

test('rejects the removed Chat alias and keeps the Home destination selected', async () => {
  const chatRenderer = await renderApp('Chat');
  const chatOutput = JSON.stringify(chatRenderer.toJSON());
  expect(chatOutput).toContain('Search Omi');
  expect(chatOutput).not.toContain('Ask anything...');
  expect(chatOutput).not.toContain('I’m ready.');

  const homeRenderer = await renderApp();
  const homeOutput = JSON.stringify(homeRenderer.toJSON());
  expect(homeOutput).toContain('Search Omi');
  expect(homeOutput).not.toContain('I’m ready.');
});

test('keeps wide browser-like surfaces separate from the native macOS workspace', async () => {
  mockPlatformOS = 'web';
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());
  const tabs = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  );

  expect(output).toContain('Search Omi');
  expect(output).toContain('Your Omi, at a glance');
  expect(output).toContain(
    'Device status and the conversations and memories saved for you.',
  );
  expect(output).not.toContain('Search what you’ve seen and heard');
  expect(output).not.toContain('QA bridge check');
  expect(output).toContain('Open Chat');
  expect(output).not.toContain('I’m ready.');
  expect(output).not.toContain('Ask anything...');
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Search Home')
      .props.autoFocus,
  ).toBeUndefined();
  expect(mockSearchFocus).not.toHaveBeenCalled();
  expect(output).not.toContain('Omi connection');
  expect(output).not.toContain('No nearby devices');
  expect(tabs.map(tab => tab.props.children[1].props.children)).toEqual([
    'Home',
    'Conversations',
    'Memories',
    'Tasks',
    'Connectors',
    'Settings',
  ]);
  expect(tabs[0].props.accessibilityState).toEqual({
    selected: true,
  });
  expect(tabs[1].props.accessibilityState).toEqual({
    selected: false,
  });
  const tablist = renderer.root.find(
    node => node.props.accessibilityRole === 'tablist',
  );
  expect(tablist.props.style).toEqual(
    expect.arrayContaining([
      expect.objectContaining({width: expect.objectContaining({value: 72})}),
    ]),
  );
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 180, toValue: 1}),
  );
  expect(
    renderer.root.findAll(node => String(node.type) === 'House'),
  ).toHaveLength(1);
  expect(
    renderer.root.findAll(node => String(node.type) === 'GanttChartSquare'),
  ).toHaveLength(1);
  expect(
    renderer.root.findAll(node => String(node.type) === 'Brain'),
  ).toHaveLength(1);
  expect(
    renderer.root.findAll(node => String(node.type) === 'ListChecks'),
  ).toHaveLength(1);
});

test('renders the v4-style Home hierarchy: top pendant, live status, Currents, device management, then the bottom search dock', async () => {
  mockViewportWidth = 390;
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());

  expect(output).toContain('Home pendant');
  expect(output).toContain('Omi');
  expect(output).toContain('Checking Bluetooth…');
  expect(output).not.toContain('82% battery');
  expect(output).toContain('Currents');
  expect(output).toContain('QA bridge check');
  expect(output).toContain('Devices');
  expect(output).toContain('Checking Bluetooth…');
  expect(output).toContain('Search Omi');
  expect(output).toContain('Home search dock');
  expect(output).not.toContain('HOME');
  expect(output).not.toContain('LATEST');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home pendant status',
    ),
  ).toBeDefined();
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home currents',
    ).props.style,
  ).toEqual(expect.objectContaining({gap: 10}));
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home devices',
    ),
  ).toBeDefined();

  const pendant = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home pendant',
  );
  expect(
    pendant.find(node => String(node.type) === 'Image').props.style,
  ).toEqual(
    expect.arrayContaining([
      expect.objectContaining({height: 210, width: 210}),
    ]),
  );
  const dock = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home search dock',
  );
  expect(dock.props.style).toEqual(
    expect.arrayContaining([
      expect.objectContaining({marginTop: 'auto'}),
      expect.objectContaining({backgroundColor: '#222621', minHeight: 60}),
    ]),
  );
});

test('keeps search results hidden until a search begins while retaining the v4 Currents feed', async () => {
  mockViewportWidth = 390;
  const renderer = await renderApp();
  const beforeSearch = JSON.stringify(renderer.toJSON());

  expect(beforeSearch).toContain('Home pendant');
  expect(beforeSearch).toContain('Omi');
  expect(beforeSearch).toContain('Currents');
  expect(beforeSearch).toContain('QA bridge check');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home search results',
    ),
  ).toHaveLength(0);
  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  await ReactTestRenderer.act(async () => search.props.onChangeText('bridge'));

  expect(JSON.stringify(renderer.toJSON())).toContain('QA bridge check');
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 180, toValue: 1}),
  );
});

test('shows the desktop chronological spine at rest and filters that same loaded list in place', async () => {
  mockPlatformOS = 'macos';
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    }
    if (request.path.startsWith('/v1/conversations')) {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'older-conversation',
            structured: {title: 'Older conversation', overview: 'Earlier'},
            created_at: '2026-08-07T09:00:00.000Z',
            updated_at: '2026-08-07T09:00:00.000Z',
            started_at: '2026-08-07T09:00:00.000Z',
            finished_at: '2026-08-07T09:10:00.000Z',
            source: 'omi',
            status: 'completed',
            discarded: false,
            starred: false,
            visibility: 'private',
            is_locked: false,
            folder_id: null,
          },
        ]),
      };
    }
    const tasks = request.path === '/v1/tasks';
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({
        contractVersion: '1.0.0',
        items: tasks
          ? []
          : [
              {
                id: 'newer-memory',
                text: 'Newer memory',
                citations: [],
                provenance: {
                  synthesisVersion: 'v1',
                  inputDigest: 'input',
                  outputDigest: 'output',
                },
                updatedAt: Date.parse('2026-08-08T09:00:00.000Z') / 1000,
              },
            ],
        window: {
          status: 'complete',
          complete: true,
          hasMore: false,
          nextCursor: null,
        },
        completeness: {
          version: tasks ? 'tasks-completeness-v1' : 'recall-completeness-v1',
          status: 'complete',
          reasons: [],
        },
        absence: null,
      }),
    };
  });

  const renderer = await renderApp();
  const beforeSearch = JSON.stringify(renderer.toJSON());
  expect(beforeSearch).toContain('Newer memory');
  expect(beforeSearch).toContain('Older conversation');
  expect(beforeSearch.indexOf('Newer memory')).toBeLessThan(
    beforeSearch.indexOf('Older conversation'),
  );
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home chronological timeline',
    ),
  ).toBeDefined();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('');
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('newer');
  });
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Newer memory');
  expect(output).not.toContain('Older conversation');
  expect(output).not.toContain('Search conversations, memories, and tasks');
  expect(output).not.toContain('Search what you’ve seen and heard');
  expect(output).not.toContain('HOME');
  expect(output).not.toContain('LATEST');
  const filters = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'button' &&
        node.props.accessibilityLabel === undefined,
    )
    .map(node => node.props.children.props?.children)
    .filter(Boolean);
  expect(filters).toEqual([]);
  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  expect(search.props.autoFocus).toBeUndefined();
  expect(search.props.showSoftInputOnFocus).toBe(false);
  await ReactTestRenderer.act(async () => search.props.onChangeText('missing'));
  expect(JSON.stringify(renderer.toJSON())).toContain('No results');
  await ReactTestRenderer.act(async () => search.props.onChangeText(''));
  expect(JSON.stringify(renderer.toJSON())).toContain('Older conversation');
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Search Home')
      .props.value,
  ).toBe('');
});

test('keeps chat inside the Home destination', async () => {
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  const tabs = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  );
  expect(tabs[0].props.accessibilityState.selected).toBe(true);
  expect(
    tabs.slice(1).every(tab => tab.props.accessibilityState.selected === false),
  ).toBe(true);
  expect(
    tabs.every(tab => tab.props.children[0].props.accessible === false),
  ).toBe(true);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Home stage'),
  ).toBeDefined();
  expect(JSON.stringify(renderer.toJSON())).toContain('Ask anything...');
});

test('routes the native macOS search command to Home and focuses search', async () => {
  mockPlatformOS = 'macos';
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  mockSearchFocus.mockClear();

  await ReactTestRenderer.act(async () => mockDesktopSearchListener?.());

  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Home stage'),
  ).toBeDefined();
  expect(mockSearchFocus).toHaveBeenCalled();
});

test('does not steal keyboard focus to Home search after returning from Chat', async () => {
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  mockSearchFocus.mockClear();

  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Back to Home')
      .props.onPress();
  });

  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Home stage'),
  ).toBeDefined();
  expect(mockSearchFocus).not.toHaveBeenCalled();
});

test('shows a visible focus ring for keyboard-focused controls and search', async () => {
  const renderer = await renderApp();
  const home = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  )[0];
  await ReactTestRenderer.act(async () => home.props.onFocus({}));
  expect(home.props.style({pressed: false})).toEqual(
    expect.arrayContaining([
      expect.objectContaining({borderColor: '#78bda5', borderWidth: 1}),
    ]),
  );

  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  await ReactTestRenderer.act(async () => search.props.onFocus());
  const searchBox = search.parent!;
  expect(searchBox.props.style).toEqual(
    expect.arrayContaining([
      expect.objectContaining({borderColor: '#78bda5', borderWidth: 1}),
    ]),
  );
});

test('navigates to rewritten-backend read projections and replays the stage transition', async () => {
  const renderer = await renderApp();
  const destinations = [
    ['Conversations', 'Recaps unavailable'],
    ['Memories', 'No memories yet.'],
    ['Tasks', 'No tasks yet.'],
    ['Connectors', 'Omi cloud needs a signed-in session.'],
    ['Settings', 'Omi cloud needs a signed-in session.'],
  ];

  for (const [destination, emptyCopy] of destinations) {
    const tab = renderer.root
      .findAll(
        node =>
          String(node.type) === 'Pressable' &&
          node.props.accessibilityRole === 'tab',
      )
      .find(node => node.props.children[1].props.children === destination)!;
    await ReactTestRenderer.act(async () => {
      tab.props.onPress();
    });
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain(destination);
    expect(output).toContain(emptyCopy);
    expect(output).not.toContain('Ask anything...');
    expect(output).not.toContain('ChatSession');
    expect(
      renderer.root.find(
        node => node.props.accessibilityLabel === `${destination} stage`,
      ),
    ).toBeDefined();
  }

  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 180, toValue: 1}),
  );
  expect(Animated.spring).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      damping: 42,
      stiffness: 520,
      toValue: 156,
      useNativeDriver: true,
    }),
  );
});

test('exposes the source-grounded destination hierarchy without removed aliases', async () => {
  const renderer = await renderApp();
  const labels = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .map(node => node.props.children[1].props.children);

  expect(labels).toEqual([
    'Home',
    'Conversations',
    'Memories',
    'Tasks',
    'Connectors',
    'Settings',
  ]);
  expect(labels).not.toEqual(expect.arrayContaining(['Chat', 'Recaps']));
});

test('keeps unsupported connectors and settings truthful and non-mutating', async () => {
  const renderer = await renderApp();
  const tabs = () =>
    renderer.root.findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    );

  await ReactTestRenderer.act(async () => tabs()[4].props.onPress());
  let output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Omi cloud needs a signed-in session.');
  expect(output).toContain('Signed out');
  expect(output).not.toContain('Connect Google');
  expect(output).not.toContain('Disconnect');
  expect(output).not.toContain('v5 backend');

  await ReactTestRenderer.act(async () => tabs()[5].props.onPress());
  const privacy = renderer.root.find(
    node => node.props.accessibilityLabel === 'Privacy settings',
  );
  await ReactTestRenderer.act(async () => privacy.props.onPress());
  output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Omi cloud needs a signed-in session.');
  expect(output).not.toContain('Save settings');
  expect(output).not.toContain('v5 backend');
  expect(output).not.toContain('settings unavailable');
});

const catalogApp = {
  id: 'catalog-app-1',
  name: 'Catalog fixture app',
  description: 'A mocked catalogue record.',
  category: 'productivity',
  author: 'fixture-author',
  enabled: false,
  uid: 'user-1',
  private: false,
  official: false,
  installs: 3,
  external_integration: {webhook_url: 'https://example.test/hook'},
  connected_accounts: [],
};

function mockCloudRoutes(request: MockRequest): MockResponse | null {
  if (request.path === '/v1/apps') {
    return {id: request.id, status: 200, body: JSON.stringify([catalogApp])};
  }
  if (request.path === '/v1/apps/enabled') {
    return {id: request.id, status: 200, body: '[]'};
  }
  if (request.path === '/v1/users/profile') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({
        uid: 'user-1',
        name: 'Ada Fixture',
        email: 'ada@example.test',
      }),
    };
  }
  if (request.path === '/v1/users/me/subscription') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({
        subscription: {plan: 'basic', status: 'active'},
        transcription_seconds_used: 12,
        transcription_seconds_limit: 60,
      }),
    };
  }
  if (request.path === '/v1/users/store-recording-permission') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({store_recording_permission: false}),
    };
  }
  if (request.path === '/v1/users/training-data-opt-in') {
    return {id: request.id, status: 200, body: JSON.stringify({opted_in: false})};
  }
  if (request.path === '/v1/users/private-cloud-sync') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({private_cloud_sync_enabled: true}),
    };
  }
  if (request.path === '/v1/users/developer/webhooks/status') {
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({memory_created: {enabled: true, url: null}}),
    };
  }
  return null;
}

test('renders an honest empty catalogue when the signed-in cloud returns no apps', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {id: request.id, status: 200, body: '[]'};
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: '[]'};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp('Connectors');
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Explore');
  expect(output).toContain('No apps were returned by the catalogue.');
  expect(output).toContain('No installed apps.');
  expect(output).toContain('No apps owned by this account.');
  expect(output).toContain(
    'No apps with an external service connection were returned.',
  );
  expect(output).not.toContain('Connect Google');
  expect(output).not.toContain('v5 backend');
});

test('lists mocked cloud apps and reports a real install failure', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    const cloud = mockCloudRoutes(request);
    if (cloud !== null) {
      return cloud;
    }
    if (request.path.startsWith('/v1/apps/enable')) {
      return {id: request.id, status: 400, body: '{"detail":"setup incomplete"}'};
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp('Connectors');
  let output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Catalog fixture app');
  expect(output).toContain('A mocked catalogue record.');
  expect(output).toContain('Not installed');
  expect(output).not.toContain('Connect Google');
  const install = renderer.root.findAll(
    node => node.props.accessibilityLabel === 'Install Catalog fixture app',
  )[0];
  await ReactTestRenderer.act(async () => {
    await install.props.onPress();
  });
  output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('desktop-app-enable failed (400)');
  expect(output).toContain('Not installed');
  expect(output).not.toContain('Installed ·');
});

test('shows mocked account settings without inventing missing controls', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    return mockCloudRoutes(request) ?? mockBackendResponse(request);
  });
  const renderer = await renderApp('Settings');
  let output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Ada Fixture');
  expect(output).toContain('ada@example.test');
  expect(output).toContain('user-1');
  expect(output).toContain('basic · active');
  expect(output).toContain('Sign out');
  expect(output).toContain(
    "Leave this app's cloud session. Your Omi account stays in the cloud.",
  );
  expect(output).not.toContain('Sign out is not exposed by this app session');
  expect(output).not.toContain('Save settings');
  const privacy = renderer.root.find(
    node => node.props.accessibilityLabel === 'Privacy settings',
  );
  await ReactTestRenderer.act(async () => privacy.props.onPress());
  output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Cloud recording storage is off.');
  expect(output).toContain('This account has not opted in to training data.');
  expect(output).toContain('Private cloud sync is on.');
  expect(output).not.toContain('Export started');
});

test('signs out of Settings and returns the signed-out empty state', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.signOut.mockImplementation(async () => {
    mockAuth.hasCloudSession.mockResolvedValue(false);
    return {signedOut: true};
  });
  mockBackend.request.mockImplementation(async request => {
    return mockCloudRoutes(request) ?? mockBackendResponse(request);
  });
  const renderer = await renderApp('Settings');
  expect(JSON.stringify(renderer.toJSON())).toContain('Ada Fixture');
  const signOut = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign out',
  );

  await ReactTestRenderer.act(async () => {
    await signOut.props.onPress();
  });

  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  expect(mockAuth.hasCloudSession).toHaveBeenCalled();
  await expect(mockAuth.hasCloudSession()).resolves.toBe(false);
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Omi cloud needs a signed-in session.');
  expect(output).toContain('Sign in');
  expect(output).not.toContain('Ada Fixture');
  expect(output).not.toContain('user-1');
});

test('keeps Settings signed in when native sign-out fails', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.signOut.mockRejectedValue(
    new Error('Could not clear the Omi cloud session'),
  );
  mockBackend.request.mockImplementation(async request => {
    return mockCloudRoutes(request) ?? mockBackendResponse(request);
  });
  const renderer = await renderApp('Settings');
  const signOut = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign out',
  );

  await ReactTestRenderer.act(async () => {
    await signOut.props.onPress();
  });

  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Ada Fixture');
  expect(output).toContain('Could not clear the Omi cloud session');
  expect(output).not.toContain('Omi cloud needs a signed-in session.');
});

test('returns to first-run onboarding after macOS sign-out clears the session', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.signOut.mockImplementation(async () => {
    mockAuth.hasCloudSession.mockResolvedValue(false);
    return {signedOut: true};
  });
  mockBackend.request.mockImplementation(async request => {
    return mockCloudRoutes(request) ?? mockBackendResponse(request);
  });
  const renderer = await renderApp('Settings');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toHaveLength(0);
  const signOut = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign out',
  );

  await ReactTestRenderer.act(async () => {
    await signOut.props.onPress();
  });

  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  expect(mockAuth.hasCloudSession).toHaveBeenCalled();
  await expect(mockAuth.hasCloudSession()).resolves.toBe(false);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toBeDefined();
  expect(JSON.stringify(renderer.toJSON())).toContain('Welcome');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Home desktop timeline surface' ||
        node.props.accessibilityLabel === 'Desktop application chrome',
    ),
  ).toHaveLength(0);
});


test('macOS sign-out stays first-run even when an environment token remains in this process', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.signOut.mockImplementation(async () => {
    // Native latch: OMI_CLOUD_API_TOKEN / OMI_API_TOKEN must not resurrect
    // hasCloudSession after an explicit Settings sign-out.
    mockAuth.hasCloudSession.mockResolvedValue(false);
    return {signedOut: true};
  });
  mockBackend.request.mockImplementation(async request => {
    return mockCloudRoutes(request) ?? mockBackendResponse(request);
  });
  const renderer = await renderApp('Settings');
  expect(JSON.stringify(renderer.toJSON())).toContain('Ada Fixture');
  const signOut = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign out',
  );

  await ReactTestRenderer.act(async () => {
    await signOut.props.onPress();
  });

  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  await expect(mockAuth.hasCloudSession()).resolves.toBe(false);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toBeDefined();
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Welcome');
  expect(output).not.toContain('Ada Fixture');
  expect(output).not.toContain('user-1');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Home desktop timeline surface' ||
        node.props.accessibilityLabel === 'Desktop application chrome',
    ),
  ).toHaveLength(0);
});

test('renders memory body separately from provenance and searches only loaded rows', async () => {
  const paths: string[] = [];
  mockBackend.request.mockImplementation(async request => {
    paths.push(request.path);
    if (request.path === '/v1/memories?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          contractVersion: '1.0.0',
          items: [
            {
              id: 'memory-1',
              text: 'quiet-river-lantern: The launch is Friday.',
              citations: ['citation-v1:launch'],
              provenance: {
                synthesisVersion: 'synthesis-v1',
                inputDigest: 'input',
                outputDigest: 'output',
              },
              updatedAt: 1785900200,
            },
            {
              id: 'memory-2',
              text: 'Lunch was outside.',
              citations: [],
              provenance: {
                synthesisVersion: 'synthesis-v1',
                inputDigest: 'input-2',
                outputDigest: 'output-2',
              },
            },
          ],
          window: {
            status: 'complete',
            complete: true,
            hasMore: false,
            nextCursor: null,
          },
          completeness: {
            version: 'recall-completeness-v1',
            status: 'complete',
            reasons: [],
          },
          absence: null,
        }),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  const memories = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Memories')!;
  await ReactTestRenderer.act(async () => memories.props.onPress());
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('The launch is Friday.');
  expect(rendered).toContain('Synthesized memory');
  expect(rendered).not.toContain('quiet-river-lantern');
  expect(rendered).not.toContain('synthesis-v1');
  expect(rendered).not.toContain('citation-v1:launch');
  expect(rendered).not.toContain('quiet-river-lantern: The launch is Friday.');
  const beforeSearch = paths.length;
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded memories')
      .props.onChangeText('lunch');
  });
  const filtered = JSON.stringify(renderer.toJSON());
  expect(filtered).toContain('Lunch was outside.');
  expect(filtered).not.toContain('The launch is Friday.');
  expect(paths).toHaveLength(beforeSearch);
});

test('loads the next memory page with the encoded exact cursor', async () => {
  const paths: string[] = [];
  const memoryPage = (
    text: string,
    nextCursor: string | null,
    hasMore: boolean,
  ) => ({
    contractVersion: '1.0.0',
    items: [
      {
        id: text,
        text,
        citations: [],
        provenance: {
          synthesisVersion: 'synthesis-v1',
          inputDigest: `input-${text}`,
          outputDigest: `output-${text}`,
        },
        updatedAt: 1785900200,
      },
    ],
    window: {
      status: hasMore ? 'more' : 'complete',
      complete: !hasMore,
      hasMore,
      nextCursor,
    },
    completeness: {
      version: 'recall-completeness-v1',
      status: 'complete',
      reasons: [],
    },
    absence: null,
  });
  mockBackend.request.mockImplementation(async request => {
    paths.push(request.path);
    if (request.path === '/v1/memories?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(memoryPage('First memory', 'opaque/+ =', true)),
      };
    }
    if (request.path === '/v1/memories?limit=50&cursor=opaque%2F%2B%20%3D') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(memoryPage('Older memory', null, false)),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  const memories = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Memories')!;
  await ReactTestRenderer.act(async () => memories.props.onPress());
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Load more memories')
      .props.onPress();
  });
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('First memory');
  expect(rendered).toContain('Older memory');
  expect(paths).toContain('/v1/memories?limit=50&cursor=opaque%2F%2B%20%3D');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more memories',
    ),
  ).toHaveLength(0);
});

test('groups and filters loaded tasks with completed and selectable presentation', async () => {
  const now = Date.UTC(2026, 7, 14, 12, 0) / 1000;
  const dateNow = jest.spyOn(Date, 'now').mockReturnValue(now * 1000);
  const requests: string[] = [];
  const task = (
    id: string,
    description: string,
    dueAt: number | null,
    completed = false,
  ) => ({
    id,
    description,
    completed,
    completedAt: completed ? now : null,
    dueAt,
    owner: null,
    source: 'assistant',
    provenance: ['assistant:test'],
    sortOrder: 1,
    indentLevel: 0,
    createdAt: now,
    updatedAt: now,
    revision: null,
  });
  mockBackend.request.mockImplementation(async request => {
    requests.push(request.path);
    if (request.path === '/v1/tasks') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          contractVersion: '1.0.0',
          accountEpoch: 4,
          items: [
            task('today', 'Ship desktop', now - 86400),
            task('tomorrow', 'Review notes', now + 86400),
            task('later', 'Archive paperwork', null, true),
          ],
          window: {
            status: 'incomplete',
            complete: false,
            hasMore: false,
            nextCursor: null,
          },
          completeness: {
            version: 'tasks-completeness-v1',
            status: 'degraded',
            reasons: ['source_delayed'],
          },
          absence: null,
        }),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  const tasks = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Tasks')!;
  await ReactTestRenderer.act(async () => tasks.props.onPress());
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Today');
  expect(rendered).toContain('Tomorrow');
  expect(rendered).toContain('Later');
  expect(rendered).toContain('Completed · No due date');
  expect(rendered).toContain('Tasks may be temporarily incomplete.');
  expect(rendered).not.toContain('source_delayed');
  expect(rendered).toContain('Tab · Focus');
  expect(rendered).toContain('Enter · Select');
  expect(rendered).not.toContain('New');
  expect(rendered).not.toContain('Delete');
  const completed = renderer.root.find(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityLabel === 'Completed task: Archive paperwork',
  );
  expect(completed.props.accessibilityState.selected).toBe(false);
  await ReactTestRenderer.act(async () => completed.props.onPress());
  expect(
    renderer.root.find(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityLabel === 'Completed task: Archive paperwork',
    ).props.accessibilityState.selected,
  ).toBe(true);
  const beforeSearch = requests.length;
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded tasks')
      .props.onChangeText('review');
  });
  const filtered = JSON.stringify(renderer.toJSON());
  expect(filtered).toContain('Review notes');
  expect(filtered).not.toContain('Ship desktop');
  expect(filtered).not.toContain('Archive paperwork');
  expect(requests).toHaveLength(beforeSearch);
  dateNow.mockRestore();
});

test('renders the dedicated Tasks unavailable state without mutation controls', async () => {
  mockBackend.request.mockImplementation(async request =>
    request.path === '/v1/tasks'
      ? {id: request.id, status: 503, body: null}
      : mockBackendResponse(request),
  );
  const renderer = await renderApp();
  const tasks = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Tasks')!;
  await ReactTestRenderer.act(async () => tasks.props.onPress());
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Tasks unavailable');
  expect(rendered).not.toContain('desktop-tasks-read failed (503)');
  expect(rendered).not.toContain('Create task');
  expect(rendered).not.toContain('Delete task');
});

test('discovers loaded conversations by local search, star, and date groups', async () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const dateNow = jest.spyOn(Date, 'now').mockReturnValue(now);
  const requests: string[] = [];
  const record = (
    id: string,
    title: string,
    overview: string,
    startedAt: string | null,
    starred: boolean,
  ) => ({
    id,
    structured: {title, overview},
    created_at: new Date(2026, 7, 12, 12, 0).toISOString(),
    updated_at: new Date(2026, 7, 14, 12, 0).toISOString(),
    started_at: startedAt,
    finished_at:
      startedAt === null
        ? null
        : new Date(new Date(startedAt).getTime() + 30 * 60_000).toISOString(),
    source: 'omi',
    status: 'completed',
    discarded: false,
    starred,
    visibility: 'private',
    is_locked: false,
    folder_id: null,
  });
  mockBackend.request.mockImplementation(async request => {
    requests.push(request.path);
    if (request.path === '/v1/conversations?limit=50&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          record(
            'today-a',
            'Morning sync',
            'Reviewed launch details',
            new Date(2026, 7, 14, 9, 0).toISOString(),
            true,
          ),
          record(
            'yesterday',
            'Design review',
            'Discussed navigation',
            new Date(2026, 7, 13, 9, 0).toISOString(),
            false,
          ),
          record(
            'today-b',
            'Afternoon sync',
            'Reviewed release details',
            new Date(2026, 7, 14, 15, 0).toISOString(),
            true,
          ),
          record('fallback', 'Saved note', 'No recording times', null, false),
        ]),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  const conversations = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Conversations')!;
  await ReactTestRenderer.act(async () => conversations.props.onPress());
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Today');
  expect(rendered).toContain('Yesterday');
  expect(rendered.indexOf('Morning sync')).toBeLessThan(
    rendered.indexOf('Afternoon sync'),
  );
  expect(rendered).toContain('Duration unavailable');
  const beforeFiltering = requests.length;
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('navigation');
  });
  let filtered = JSON.stringify(renderer.toJSON());
  expect(filtered).toContain('Design review');
  expect(filtered).not.toContain('Morning sync');
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('');
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Show starred conversations',
      )
      .props.onPress();
  });
  filtered = JSON.stringify(renderer.toJSON());
  expect(filtered).toContain('Morning sync');
  expect(filtered).toContain('Afternoon sync');
  expect(filtered).not.toContain('Design review');
  expect(requests).toHaveLength(beforeFiltering);
  dateNow.mockRestore();
});

test('opens a read-only selected-record pane from a loaded conversation row', async () => {
  const renderer = await renderApp();
  const conversations = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Conversations')!;

  await ReactTestRenderer.act(async () => conversations.props.onPress());
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation QA bridge check',
      )
      .props.onPress();
  });

  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('LOADED LIST METADATA');
  expect(
    renderer.root.find(
      node =>
        String(node.type) === 'Text' &&
        Array.isArray(node.props.children) &&
        node.props.children[0] === 'Status · ' &&
        node.props.children[1] === 'completed',
    ),
  ).toBeDefined();
  expect(output).toContain('Unlocked record');
  expect(output).toContain('Active record');
  expect(output).toContain(
    'No fetched conversation detail, transcript, playback, folders, or actions are shown here.',
  );
  expect(mockBackend.request).not.toHaveBeenCalledWith(
    expect.objectContaining({path: '/v1/conversations/conversation-1'}),
  );
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      )
      .props.onChangeText('does not match');
  });
  expect(JSON.stringify(renderer.toJSON())).toContain('Select a conversation');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'LOADED LIST METADATA',
  );
});

test('keeps successful reads visible and reports each unavailable domain', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    }
    if (request.path === '/v1/conversations?limit=50&offset=0') {
      return {id: request.id, status: 503, body: null};
    }
    const tasks = request.path === '/v1/tasks';
    return {
      id: request.id,
      status: 200,
      body: JSON.stringify({
        contractVersion: '1.0.0',
        items: tasks
          ? [
              {
                id: 'task1_visible',
                description: 'Keep the successful task',
                completed: false,
                completedAt: null,
                dueAt: null,
                owner: null,
                source: 'assistant',
                provenance: ['assistant:test'],
                sortOrder: 1,
                indentLevel: 0,
                createdAt: 1,
                updatedAt: 1,
                revision: 'revision-1',
              },
            ]
          : [],
        window: {
          status: tasks ? 'incomplete' : 'complete',
          complete: !tasks,
          hasMore: false,
          nextCursor: null,
        },
        completeness: {
          version: tasks ? 'tasks-completeness-v1' : 'recall-completeness-v1',
          status: tasks ? 'incomplete' : 'complete',
          reasons: tasks ? ['pending_writes'] : [],
        },
        absence: null,
      }),
    };
  });

  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('saved');
  });
  const home = JSON.stringify(renderer.toJSON());
  expect(home).not.toContain('Keep the successful task');
  expect(home).toContain('Conversations');
  expect(home).toContain('are unavailable.');
  expect(home).not.toContain('desktop-conversations-read failed (503)');
  expect(home).not.toContain('Tasks are incomplete.');
  expect(home).not.toContain('pending_writes');

  const conversations = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Conversations')!;
  await ReactTestRenderer.act(async () => conversations.props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Conversations could not be loaded.',
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'desktop-conversations-read failed (503)',
  );

  const tasks = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Tasks')!;
  await ReactTestRenderer.act(async () => tasks.props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Keep the successful task',
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Tasks are incomplete.');
});

test('explains local backend configuration failure with one retryable Home state', async () => {
  const configurationError = Object.assign(
    new Error('Native HTTP configuration is unavailable'),
    {code: 'OMI_HTTP_UNCONFIGURED'},
  );
  mockBackend.request.mockRejectedValue(configurationError);

  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('missing');
  });

  const unavailable = JSON.stringify(renderer.toJSON());
  expect(unavailable).toContain(
    'Sign in to Omi cloud to load conversations and memories.',
  );
  expect(unavailable).not.toContain('h.omi.me');
  expect(unavailable).not.toContain('OMI_LOCAL_API_CLIENT_ID');
  expect(unavailable).not.toContain('Conversations are unavailable.');
  expect(unavailable).not.toContain('Memories are unavailable.');

  const retry = renderer.root.find(
    node => node.props.accessibilityLabel === 'Retry saved data',
  );
  expect(retry.props.onPress).toEqual(expect.any(Function));

  mockBackend.request.mockImplementation(async request =>
    mockBackendResponse(request),
  );
  await ReactTestRenderer.act(async () => {
    await retry.props.onPress();
  });

  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Sign in to Omi cloud to load conversations and memories.',
  );
});

test('signs in from macOS Home recovery and retries cloud reads', async () => {
  mockPlatformOS = 'macos';
  mockBackend.request.mockRejectedValue(
    Object.assign(new Error('Native HTTP configuration is unavailable'), {
      code: 'OMI_HTTP_UNCONFIGURED',
    }),
  );

  const renderer = await renderApp();
  const before = JSON.stringify(renderer.toJSON());
  expect(before).not.toContain('h.omi.me');
  const signIn = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign in',
  );

  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockBackend.request.mockImplementation(async request =>
    mockBackendResponse(request),
  );
  await ReactTestRenderer.act(async () => {
    await signIn.props.onPress();
  });

  expect(mockAuth.signIn).toHaveBeenCalledTimes(1);
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(mockBackend.request.mock.calls.length).toBeGreaterThan(3);
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Sign in'),
  ).toHaveLength(0);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Sign in to Omi cloud to load conversations and memories.',
  );
});

test('presents a full, truthful wide Home unavailable state without leaking endpoint errors', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    }
    return request.path.startsWith('/v1/conversations') ||
      request.path.startsWith('/v1/memories')
      ? {
          id: request.id,
          status: 503,
          body: JSON.stringify({
            error: {
              code: 'projection_unavailable',
              retryable: true,
              action: 'retry',
            },
          }),
        }
      : {id: request.id, status: 503, body: null};
  });

  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('morning');
  });

  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Your Omi, at a glance');
  expect(output).toContain('Saved data is unavailable.');
  expect(output).toContain(
    'Saved conversations and memories are not available from this Omi service yet. Retry after its persisted projections are connected.',
  );
  expect(output).not.toContain('desktop-conversations-read failed (503)');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home desktop query surface',
    ),
  ).toHaveLength(0);
});

test('shows actionable service-unavailable copy when the local backend transport fails', async () => {
  const transportError = Object.assign(
    new Error('Native HTTP transport failed'),
    {code: 'OMI_HTTP_TRANSPORT'},
  );
  mockBackend.request.mockRejectedValue(transportError);

  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search Home')
      .props.onChangeText('morning');
  });

  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain(
    'Omi cloud at https://api.omi.me is unavailable. Check the connection, then retry.',
  );
  expect(output).not.toContain('127.0.0.1:8787');
  expect(output).not.toContain('Native HTTP transport failed');
  expect(output).not.toContain('desktop-conversations-read failed');

  const retry = renderer.root.find(
    node => node.props.accessibilityLabel === 'Retry saved data',
  );
  expect(retry.props.onPress).toEqual(expect.any(Function));
});

test('uses a full, navigation-free pane on mobile', async () => {
  mockViewportWidth = 390;
  const renderer = await renderApp();

  expect(
    renderer.root.findAll(node => node.props.accessibilityRole === 'tablist'),
  ).toHaveLength(0);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Search Home')
      .props.value,
  ).toBe('');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home pendant',
    ),
  ).toBeDefined();
});

test('fills the macOS content area with first-run onboarding', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);

  const renderer = await renderApp();
  const onboarding = renderer.root.find(
    node => node.props.accessibilityLabel === 'First-run onboarding',
  );
  const onboardingStyles = ([] as Array<Record<string, unknown>>)
    .concat(onboarding.props.style)
    .filter(style => style != null);
  const rendered = JSON.stringify(renderer.toJSON());

  expect(onboardingStyles).toEqual(
    expect.arrayContaining([
      expect.objectContaining({alignSelf: 'stretch', flex: 1}),
    ]),
  );
  expect(rendered).toContain('Welcome');
  expect(rendered).not.toContain('h.omi.me');
  expect(
    onboarding.find(node => node.props.accessibilityLabel === 'Sign in'),
  ).toBeDefined();
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Home desktop timeline surface' ||
        node.props.accessibilityLabel === 'Home saved-data recovery',
    ),
  ).toHaveLength(0);
  expect(JSON.stringify(onboarding.props.style)).not.toContain('maxWidth');
  expect(rendered).not.toContain('maxWidth":440');
  expect(
    onboarding.findAll(node =>
      [
        'Brain',
        'GanttChartSquare',
        'House',
        'ListChecks',
        'PanelLeft',
        'PanelLeftClose',
        'Search',
      ].includes(String(node.type)),
    ),
  ).toHaveLength(0);
  expect(rendered).not.toContain('Search Omi');
  expect(rendered).not.toContain('Home search dock');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Desktop application chrome' ||
        node.props.accessibilityLabel === 'Home navigation' ||
        node.props.accessibilityLabel === 'Home search dock',
    ),
  ).toHaveLength(0);
  const workspace = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop workspace material',
  );
  expect(workspace.props.glassCornerRadius).toBe(0);
  expect(workspace.props.pointerEvents).toBe('none');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding material',
    ),
  ).toHaveLength(0);
  const inkDots = renderer.root.findAll(node => {
    if (String(node.type) !== 'AnimatedView') {
      return false;
    }
    return ([] as Array<Record<string, unknown>>)
      .concat(node.props.style)
      .filter((entry): entry is Record<string, unknown> => entry != null)
      .some(entry => {
        const color = String(entry.backgroundColor ?? '')
          .trim()
          .toLowerCase();
        return color === '#ffffff' || color === '#fff' || color === 'white';
      });
  });
  expect(inkDots).toHaveLength(8);
  const rainbow = Array.from({length: 8}, (_, index) =>
    omiDotColor('omi', index),
  );
  for (const color of rainbow) {
    expect(rendered).not.toContain(color);
  }
});

test('hides Search Omi and Home search dock during first-run onboarding', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);

  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());

  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toBeDefined();
  expect(output).toContain('Welcome');
  expect(output).toContain('Sign in');
  expect(output).not.toContain('Search Omi');
  expect(output).not.toContain('Home search dock');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Desktop application chrome' ||
        node.props.accessibilityLabel === 'Home navigation',
    ),
  ).toHaveLength(0);
});

test('keeps macOS Home gated while the auth probe is unresolved', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockImplementation(
    () => new Promise(() => {}),
  );

  const renderer = await renderApp();

  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toBeDefined();
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home desktop timeline surface',
    ),
  ).toHaveLength(0);
});

test('keeps macOS Home gated when the auth probe rejects', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockRejectedValue(
    new Error('Auth probe failed'),
  );

  const renderer = await renderApp();

  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toBeDefined();
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home desktop timeline surface',
    ),
  ).toHaveLength(0);
});

test('skips first-run onboarding for a returning macOS user', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(false);

  const renderer = await renderApp();

  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Desktop application chrome',
    ),
  ).toBeDefined();
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home desktop timeline surface',
    ),
  ).toBeDefined();
});

test('skips onboarding and records completion when a cloud session exists', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const renderer = await renderApp();

  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toHaveLength(0);
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home desktop timeline surface',
    ),
  ).toBeDefined();
});

test('reduce-motion first-run is a static white mark on shared glass', async () => {
  mockPlatformOS = 'macos';
  mockReduceMotion = true;
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    mockReduceMotionListener?.(true);
    await Promise.resolve();
  });

  const workspace = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop workspace material',
  );
  expect(workspace.props.pointerEvents).toBe('none');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding material',
    ),
  ).toHaveLength(0);
  const dots = renderer.root.find(
    node =>
      node.props.identity === 'omi' &&
      node.props.size === 104 &&
      node.props.tone === 'ink',
  );
  expect(dots.props).toMatchObject({
    animate: false,
    reduceMotion: true,
    tone: 'ink',
  });
  const stage = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home stage',
  );
  expect(stage.props.style[1].opacity.setValue).toHaveBeenCalledWith(1);
  expect(
    stage.props.style[1].transform[0].translateY.setValue,
  ).toHaveBeenCalledWith(0);
});

test('signs in from first-run onboarding, records completion, and shows Home', async () => {
  mockPlatformOS = 'macos';
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  const renderer = await renderApp();
  const signIn = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sign in',
  );

  await ReactTestRenderer.act(async () => {
    await signIn.props.onPress();
  });

  expect(mockAuth.signIn).toHaveBeenCalledTimes(1);
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home desktop timeline surface',
    ),
  ).toBeDefined();
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Desktop application chrome',
    ),
  ).toBeDefined();
  expect(JSON.stringify(renderer.toJSON())).toContain('Search Omi');
  expect(JSON.stringify(renderer.toJSON())).toContain('Home search dock');
});

test('keeps macOS Home as search chrome followed by compact navigation and timeline', async () => {
  mockPlatformOS = 'macos';
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());
  const searchIndex = output.indexOf('Home search dock');
  const homeIndex = output.indexOf('Home navigation');
  const timelineIndex = output.indexOf('Home chronological timeline');

  expect(searchIndex).toBeGreaterThan(-1);
  expect(homeIndex).toBeGreaterThan(searchIndex);
  expect(output).not.toContain('Home rewind context');
  expect(output).not.toContain('Conversations and memories saved on this Mac.');
  expect(timelineIndex).toBeGreaterThan(homeIndex);
  expect(output).not.toContain('Home query island');
  expect(output).not.toContain('Home results panel');
  expect(output).not.toContain('What matters now');
  expect(output).not.toContain('home-workspace-material');
  expect(output).not.toContain('Workspace 2');
  expect(output).not.toContain('More navigation');
  const material = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop workspace material',
  );
  expect(material.props.glassCornerRadius).toBe(0);
  expect(material.props.style).toEqual(
    expect.objectContaining({bottom: 0, left: 0, right: 0, top: 0}),
  );
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Desktop navigation material' ||
        node.props.accessibilityLabel === 'Home desktop material',
    ),
  ).toHaveLength(0);
  const chrome = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop application chrome',
  );
  const chromeStyles = ([] as Array<Record<string, unknown>>)
    .concat(chrome.props.style)
    .filter(style => style != null);
  const chromeStyle = Object.assign({}, ...chromeStyles);
  expect(chromeStyle.height).toBeGreaterThanOrEqual(36);
  expect(chromeStyle.height).toBeLessThanOrEqual(40);
  expect(chromeStyle.borderRadius ?? 0).toBe(0);
  expect(chromeStyle.marginHorizontal ?? 0).toBe(0);
  expect(chromeStyle.marginTop ?? 0).toBe(0);
  expect(
    chromeStyle.paddingHorizontal ?? chromeStyle.paddingLeft,
  ).toBeGreaterThanOrEqual(12);
  expect(chromeStyle.paddingLeft ?? chromeStyle.paddingHorizontal).toBe(
    chromeStyle.paddingRight ?? chromeStyle.paddingHorizontal,
  );
  expect(chromeStyle.paddingLeft).not.toBe(78);
  const applicationSurface = renderer.root.find(
    node => String(node.type) === 'SafeAreaView',
  );
  const applicationEdges = applicationSurface.props.edges as
    | string[]
    | undefined;
  expect(
    applicationEdges === undefined || applicationEdges.includes('top'),
  ).toBe(true);
  expect(JSON.stringify(chrome.props.style)).not.toContain('borderTopWidth');
  expect(JSON.stringify(chrome.props.style)).not.toContain(
    'rgba(255, 255, 255',
  );
  const homeSurface = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home desktop timeline surface',
  );
  expect(homeSurface.props.style).toEqual(
    expect.objectContaining({
      alignSelf: 'stretch',
      backgroundColor: 'transparent',
      borderRadius: 0,
      flex: 1,
    }),
  );
  expect(JSON.stringify(homeSurface.props.style)).not.toContain(
    'borderTopWidth',
  );
  const homeNav = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home navigation',
  );
  expect(homeNav.props.accessibilityRole).toBe('button');
  expect(homeNav.props.accessibilityState).toEqual({expanded: false});
  expect(
    homeNav.findAll(
      node => String(node.type) === 'Text' && node.props.children === 'Home',
    ),
  ).not.toHaveLength(0);
  const homeIcon = homeNav.find(node => node.props.symbolName !== undefined);
  expect(homeIcon.props.symbolColor).toBe('#f2f4f1');
  const searchDock = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home search dock',
  );
  const dockStyles = ([] as Array<Record<string, unknown>>)
    .concat(searchDock.props.style)
    .filter(style => style != null);
  const desktopDockStyle = dockStyles.find(
    style => style.paddingHorizontal !== undefined,
  );
  expect(desktopDockStyle).toEqual(
    expect.objectContaining({
      alignItems: 'center',
      flex: 1,
      flexGrow: 1,
      maxWidth: '100%',
      paddingHorizontal: expect.any(Number),
    }),
  );
  expect(desktopDockStyle!.paddingHorizontal).toBeGreaterThanOrEqual(12);
  expect(
    dockStyles.some(
      style =>
        style.borderTopWidth != null ||
        (style.borderWidth != null &&
          style.borderWidth !== 0 &&
          String(style.borderColor ?? '').includes('255, 255, 255')),
    ),
  ).toBe(false);
  const homeSearch = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  const searchStyles = ([] as Array<Record<string, unknown>>)
    .concat(homeSearch.props.style)
    .filter(style => style != null);
  expect(searchStyles).not.toEqual(
    expect.arrayContaining([
      expect.objectContaining({height: 24, paddingVertical: 0}),
    ]),
  );
  expect(homeSearch.props.placeholder).toBe('Search Omi');
  expect(homeSearch.props.placeholderTextColor).toBe('#c8cbc6');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home navigation',
    ),
  ).toBeDefined();
  const navigation = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home navigation',
  ).parent;
  expect(navigation?.props.style).toEqual(
    expect.objectContaining({flexShrink: 0}),
  );
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Conversations navigation',
    ),
  ).toHaveLength(0);
  const workspace = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop workspace material',
  );
  expect(workspace.props.pointerEvents).toBe('none');
  const homeSymbol = homeNav.find(node => node.props.symbolName !== undefined);
  expect(homeSymbol.props.symbolName).toBe('house');
  expect(
    chrome.findAll(node =>
      [
        'Brain',
        'GanttChartSquare',
        'House',
        'ListChecks',
        'PanelLeft',
        'PanelLeftClose',
        'Search',
      ].includes(String(node.type)),
    ),
  ).toHaveLength(0);
});

test('renders one compact macOS Home recovery instead of a filled error card', async () => {
  mockPlatformOS = 'macos';
  mockBackend.request.mockRejectedValue(
    Object.assign(new Error('Native HTTP transport failed'), {
      code: 'OMI_HTTP_TRANSPORT',
    }),
  );

  const renderer = await renderApp();
  const recovery = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home saved-data recovery',
  );
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Saved data unavailable');
  expect(rendered).toContain(
    'Omi cloud at https://api.omi.me is unavailable. Check the connection, then retry.',
  );
  expect(rendered).not.toContain('Native HTTP transport failed');
  expect(rendered).not.toContain('Workspace 2');
  expect(recovery.props.style).toEqual(
    expect.objectContaining({maxWidth: 440}),
  );
  const recoveryCopy = recovery.findAll(
    node =>
      String(node.type) === 'Text' && typeof node.props.children === 'string',
  );
  expect(
    recoveryCopy.some(
      node =>
        String(node.props.children).includes('https://api.omi.me') &&
        node.props.style.color === '#dfe2dd',
    ),
  ).toBe(true);
  expect(JSON.stringify(recovery.props.style)).not.toContain('shadowColor');
  expect(recovery.props.style.backgroundColor).toBeUndefined();
  expect(
    recovery.findAll(
      node =>
        node.props.accessibilityLabel === 'Retry saved data' &&
        typeof node.props.onPress === 'function',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home rewind context',
    ),
  ).toHaveLength(0);
});

test('surfaces the typed memories failure when conversations fails untyped', async () => {
  mockPlatformOS = 'macos';
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    }
    if (request.path.startsWith('/v1/conversations')) {
      return {id: request.id, status: 500, body: null};
    }
    return request.path.startsWith('/v1/memories')
      ? {
          id: request.id,
          status: 503,
          body: JSON.stringify({
            error: {
              code: 'projection_unavailable',
              retryable: true,
              action: 'retry',
            },
          }),
        }
      : {id: request.id, status: 503, body: null};
  });

  const renderer = await renderApp();
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain(
    'Saved conversations and memories are not available from this Omi service yet. Retry after its persisted projections are connected.',
  );
  expect(rendered).not.toContain('desktop-conversations-read failed (500)');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home saved-data recovery',
    ),
  ).toBeDefined();
});

test('shows a truthful loading timeline while a retry recovers from unavailable', async () => {
  mockPlatformOS = 'macos';
  const transportError = Object.assign(
    new Error('Native HTTP transport failed'),
    {code: 'OMI_HTTP_TRANSPORT'},
  );
  mockBackend.request.mockRejectedValue(transportError);
  const renderer = await renderApp();
  expect(JSON.stringify(renderer.toJSON())).toContain('Saved data unavailable');

  let releaseReads: Array<() => void> = [];
  mockBackend.request.mockImplementation(
    async request =>
      new Promise<MockResponse>(resolve => {
        releaseReads.push(() => resolve(mockBackendResponse(request)));
      }),
  );
  const retry = renderer.root.findAll(
    node =>
      node.props.accessibilityLabel === 'Retry saved data' &&
      typeof node.props.onPress === 'function',
  )[0];
  await ReactTestRenderer.act(async () => {
    retry.props.onPress();
  });

  const refreshing = JSON.stringify(renderer.toJSON());
  expect(refreshing).toContain('Loading timeline…');
  expect(refreshing).not.toContain('No saved conversations or memories yet.');
  expect(refreshing).not.toContain('Saved data unavailable');

  await ReactTestRenderer.act(async () => {
    releaseReads.forEach(release => release());
    await Promise.resolve();
  });

  const recovered = JSON.stringify(renderer.toJSON());
  expect(recovered).toContain('QA bridge check');
  expect(recovered).not.toContain('Loading timeline…');
});

test('opens secondary desktop destinations from the Home switcher', async () => {
  mockPlatformOS = 'macos';
  const renderer = await renderApp();

  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home navigation',
    ).props.accessibilityState,
  ).toEqual({expanded: false});
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Home navigation')
      .props.onPress();
  });
  const menu = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home destination switcher',
  );
  expect(menu).toBeDefined();
  expect(menu.props.pointerEvents).toBe('auto');
  expect(menu.props.style).toEqual(
    expect.objectContaining({
      borderWidth: 0,
      width: 224,
      zIndex: 41,
      right: 16,
    }),
  );
  const glass = renderer.root.find(
    node => node.props.accessibilityLabel === 'Desktop workspace material',
  );
  expect(glass.props.pointerEvents).toBe('none');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home navigation',
    ).props.accessibilityState,
  ).toEqual({expanded: true});
  const destinationSymbols: Record<string, string> = {
    Home: 'house',
    Conversations: 'bubble.left.and.bubble.right',
    Memories: 'brain',
    Tasks: 'checklist',
    Connectors: 'link',
    Settings: 'gearshape',
  };
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Conversations destination',
    ).props.accessibilityRole,
  ).toBe('menuitem');
  for (const destination of [
    'Home',
    'Conversations',
    'Memories',
    'Tasks',
    'Connectors',
    'Settings',
  ]) {
    const button = renderer.root.find(
      node => node.props.accessibilityLabel === `${destination} destination`,
    );
    expect(button.props.accessibilityRole).toBe('menuitem');
    expect(typeof button.props.onPress).toBe('function');
    expect(button.props.hitSlop).toEqual({
      bottom: 6,
      left: 8,
      right: 8,
      top: 6,
    });
    expect(button.props.pointerEvents).not.toBe('none');
    expect(
      button.find(node => node.props.symbolName !== undefined).props.symbolName,
    ).toBe(destinationSymbols[destination]);
  }
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks destination')
      .props.onPress();
  });
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Tasks stage'),
  ).toBeDefined();
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home destination switcher',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Home navigation',
    ).props.accessibilityState,
  ).toEqual({expanded: false});
});

test('keeps desktop hardware secondary while retaining native device actions', async () => {
  mockPlatformOS = 'macos';
  mockNative.getSnapshot.mockResolvedValue({
    audioRoute: 'phone-mic',
    background: 'inactive',
    bluetooth: 'poweredOn',
    capture: 'idle',
    captureMode: 'stream',
    devices: [
      {battery: 82, connected: true, id: 'omi-1', name: 'Omi', rssi: -54},
    ],
    lastEvent: 'Connected to Omi',
    microphone: 'granted',
    notifications: 'granted',
  });
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());
  expect(output.indexOf('Home chronological timeline')).toBeLessThan(
    output.indexOf('Home device affordance'),
  );
  const affordance = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home device affordance',
  );
  expect(affordance.props.style).toEqual(
    expect.objectContaining({minHeight: 36}),
  );
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Disconnect Omi')
      .props.onPress();
  });
  expect(mockNative.disconnectDevice).toHaveBeenCalledWith('omi-1');
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Scan for Omi devices')
      .props.onPress();
  });
  expect(mockNative.startScan).toHaveBeenCalledWith(8);
});

test.each([800, 960, 1440])(
  'keeps primary text legible over macOS glass at %ipx',
  async width => {
    mockPlatformOS = 'macos';
    mockViewportWidth = width;
    const renderer = await renderApp();
    const homeSearch = renderer.root.find(
      node => node.props.accessibilityLabel === 'Search Home',
    );

    expect(homeSearch.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({color: '#f2f4f1'})]),
    );
    expect(
      renderer.root.findAll(
        node =>
          node.props.accessibilityRole === 'tablist' &&
          Array.isArray(node.props.style),
      ),
    ).toHaveLength(0);

    await ReactTestRenderer.act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Home navigation')
        .props.onPress();
    });
    await ReactTestRenderer.act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Tasks destination')
        .props.onPress();
    });
    const tasksTitle = renderer.root
      .findAll(
        node => String(node.type) === 'Text' && node.props.children === 'Tasks',
      )
      .find(node => Array.isArray(node.props.style));
    expect(tasksTitle).toBeDefined();
    expect(tasksTitle!.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({color: '#f2f4f1'})]),
    );
  },
);

test('keeps non-macOS mobile navigation-free and pane-focused', async () => {
  mockPlatformOS = 'ios';
  mockViewportWidth = 390;
  const renderer = await renderApp();

  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Desktop navigation',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Desktop workspace material',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(node => node.props.accessibilityRole === 'tablist'),
  ).toHaveLength(0);
});

test('resizes pane and rail at their independent reference breakpoints', async () => {
  mockViewportWidth = 700;
  const tablet = await renderApp();
  expect(
    tablet.root.findAll(node => node.props.accessibilityRole === 'tablist'),
  ).toHaveLength(0);
  const tabletPane = tablet.root.find(
    node => String(node.type) === 'KeyboardAvoidingView',
  );
  expect(tabletPane.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({borderRadius: 26})]),
  );
  await ReactTestRenderer.act(async () => tablet.unmount());

  mockViewportWidth = 1000;
  const intermediate = await renderApp();
  expect(
    intermediate.root.findAll(
      node => node.props.accessibilityRole === 'tablist',
    ),
  ).toHaveLength(0);
  await ReactTestRenderer.act(async () => intermediate.unmount());

  mockViewportWidth = 1024;
  const desktop = await renderApp();
  expect(
    desktop.root.find(node => node.props.accessibilityRole === 'tablist').props
      .style,
  ).toEqual(
    expect.arrayContaining([
      expect.objectContaining({width: expect.objectContaining({value: 72})}),
    ]),
  );
});

test('expands the desktop rail to 280 with visible labels and reference timing', async () => {
  const renderer = await renderApp();
  const expand = renderer.root.find(
    node => node.props.accessibilityLabel === 'Expand sidebar',
  );

  await ReactTestRenderer.act(async () => expand.props.onPress());

  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      duration: 200,
      toValue: 280,
      useNativeDriver: false,
    }),
  );
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Collapse sidebar',
    ),
  ).toBeDefined();
  const homeLabel = renderer.root.find(
    node => String(node.type) === 'Text' && node.props.children === 'Home',
  );
  expect(homeLabel.props.style).not.toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0, width: 0})]),
  );
});

test('layers floating pane depth without native macOS shadow properties', async () => {
  mockViewportWidth = 700;
  const renderer = await renderApp();
  const depth = renderer.root.find(
    node => node.props.accessibilityLabel === 'Floating pane depth',
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('shadowOffset');
  expect(React.Children.count(depth.props.children)).toBe(3);
  expect(
    React.Children.toArray(depth.props.children).every(
      child =>
        React.isValidElement<{style: Array<{bottom?: number; top?: number}>}>(
          child,
        ) &&
        child.props.style.some(
          style => style?.top === 14 && style?.bottom === -14,
        ),
    ),
  ).toBe(true);
});

test('removes floating pane depth below 640 pixels', async () => {
  mockViewportWidth = 639;
  const renderer = await renderApp();
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Floating pane depth',
    ),
  ).toHaveLength(0);
  expect(JSON.stringify(renderer.toJSON())).not.toContain('shadowOffset');
});

test.each([
  [700, 640],
  [1000, 720],
  [1300, 820],
])(
  'a %ipx window keeps Chat scrollable with a %ipx composer',
  async (width, maxWidth) => {
    mockViewportWidth = width;
    const renderer = await renderApp();
    await ReactTestRenderer.act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Open Chat')
        .props.onPress();
    });

    expect(
      renderer.root.find(
        node => node.props.accessibilityLabel === 'Chat scroll region',
      ),
    ).toBeDefined();
    const composer = renderer.root.find(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {maxWidth?: number}) => style?.maxWidth === maxWidth,
        ),
    );
    expect(composer).toBeDefined();
  },
);

test('removes translation and skips stage fades when reduced motion is enabled', async () => {
  mockViewportWidth = 390;
  mockReduceMotion = true;
  const renderer = await renderApp();

  await ReactTestRenderer.act(async () => {
    mockReduceMotionListener?.(true);
    await Promise.resolve();
  });

  const stage = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home stage',
  );
  expect(stage.props.style[1].opacity.setValue).toHaveBeenCalledWith(1);
  expect(
    stage.props.style[1].transform[0].translateY.setValue,
  ).toHaveBeenCalledWith(0);
});

test('moves the desktop active pill directly when motion is reduced', async () => {
  mockReduceMotion = true;
  const renderer = await renderApp();
  const activePill = renderer.root.find(
    node =>
      String(node.type) === 'AnimatedView' &&
      node.props.accessibilityElementsHidden === true,
  );
  const translateY = activePill.props.style.find(
    (style: {transform?: unknown}) => style?.transform,
  ).transform[0].translateY;
  const conversations = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Conversations')!;

  await ReactTestRenderer.act(async () => conversations.props.onPress());

  expect(translateY.setValue).toHaveBeenCalledWith(52);
});

test('resizes the desktop rail directly when motion is reduced', async () => {
  mockReduceMotion = true;
  const renderer = await renderApp();
  const tablist = renderer.root.find(
    node => node.props.accessibilityRole === 'tablist',
  );
  const width = tablist.props.style.find(
    (style: {width?: {setValue?: jest.Mock}}) => style?.width?.setValue,
  ).width;

  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Expand sidebar')
      .props.onPress();
  });

  expect(width.setValue).toHaveBeenCalledWith(280);
});

test('fills, focuses, and preserves the ask pill draft from a quick prompt', async () => {
  const renderer = await renderApp();
  const openChat = renderer.root.find(
    node => node.props.accessibilityLabel === 'Open Chat',
  );
  await ReactTestRenderer.act(async () => {
    openChat.props.onPress();
  });
  const promptText = renderer.root.find(
    node =>
      String(node.type) === 'Text' &&
      node.props.children === 'What should I remember?',
  );
  const prompt = promptText.parent?.parent!;

  expect(
    renderer.root.find(node => String(node.type) === 'Paperclip').props.size,
  ).toBe(18);
  expect(
    renderer.root.find(node => String(node.type) === 'Mic').props.size,
  ).toBe(18);
  expect(
    renderer.root.find(node => String(node.type) === 'ArrowUp').props,
  ).toEqual(expect.objectContaining({size: 18, strokeWidth: 2.5}));

  mockSearchFocus.mockClear();
  await ReactTestRenderer.act(async () => {
    prompt.props.onPress();
  });

  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.value,
  ).toBe('What should I remember?');
  expect(mockSearchFocus).toHaveBeenCalledTimes(1);
});

test('matches the compact resting stage, prompt grid, and composer geometry', async () => {
  mockViewportWidth = 390;
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });

  const resting = renderer.root.find(
    node => node.props.accessibilityLabel === 'Chat resting stage',
  );
  const mark = renderer.root.find(
    node => node.props.accessibilityLabel === 'Omi',
  );
  const promptText = renderer.root.find(
    node =>
      String(node.type) === 'Text' &&
      node.props.children === 'What should I remember?',
  );
  const promptStyle = promptText.parent?.parent!.props.style({
    pressed: false,
  });
  const input = renderer.root.find(
    node => node.props.accessibilityLabel === 'Ask Omi',
  );

  expect(resting).toBeDefined();
  expect(mark.props.style).toEqual(
    expect.objectContaining({height: 40, width: 40}),
  );
  expect(
    mark.find(node => String(node.type) === 'Image').props.source.uri,
  ).toMatch(/^data:image\/png;base64,/);
  expect(JSON.stringify(promptStyle)).toContain('"flexBasis":"48%"');
  expect(input.props.style).toEqual(expect.objectContaining({maxHeight: 200}));
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 250, toValue: 1}),
  );
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {paddingHorizontal?: number}) =>
            style?.paddingHorizontal === 16,
        ),
    ),
  ).not.toHaveLength(0);

  await ReactTestRenderer.act(async () => input.props.onFocus());
  expect(
    renderer.root.find(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {borderColor?: string}) => style?.borderColor === '#626262',
        ),
    ),
  ).toBeDefined();
});

test('uses opacity-only resting-stage motion when reduced motion is enabled', async () => {
  mockViewportWidth = 390;
  mockReduceMotion = true;
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  const resting = renderer.root.find(
    node => node.props.accessibilityLabel === 'Chat resting stage',
  );

  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 1, toValue: 1}),
  );
  expect(resting.props.style[1].transform[0].translateY.value).toBe(0);
});

test('renders saved Chat history as a wide transcript without the resting hub', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          messages: [
            chatMessage('saved-human', 'Saved human', 'human', null),
            chatMessage('saved-ai', 'Saved answer', 'ai', 'completed'),
          ],
          page: {olderCursor: null, hasOlder: false},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Saved human');
  expect(rendered).toContain('Saved answer');
  expect(rendered).not.toContain('I’m ready.');
  expect(rendered).not.toContain('What did I talk about today?');
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' && node.props.style?.maxWidth === 760,
    ),
  ).not.toHaveLength(0);
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {backgroundColor?: string}) =>
            style?.backgroundColor === '#2c2c33',
        ),
    ),
  ).not.toHaveLength(0);
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {maxWidth?: string}) => style?.maxWidth === '75%',
        ),
    ),
  ).not.toHaveLength(0);
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        node.props.style?.height === 40 &&
        node.props.style?.width === 40,
    ),
  ).not.toHaveLength(0);
  const avatarDots = renderer.root.findAll(
    node =>
      String(node.type) === 'AnimatedView' &&
      Array.isArray(node.props.style) &&
      node.props.style[0]?.height === 5 &&
      node.props.style[0]?.width === 5,
  );
  expect(avatarDots).toHaveLength(8);
  expect(
    avatarDots.every(dot => {
      const motion = dot.props.style.find((style: {transform?: unknown}) =>
        Array.isArray(style?.transform),
      );
      return Array.isArray(motion?.transform) && motion.transform.length === 2;
    }),
  ).toBe(true);
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {paddingHorizontal?: number; paddingVertical?: number}) =>
            style?.paddingHorizontal === 20 && style?.paddingVertical === 12,
        ),
    ),
  ).not.toHaveLength(0);
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {fontSize?: number}) => style?.fontSize === 12,
        ),
    ),
  ).not.toHaveLength(0);
  const stableRows = renderer.root.findAll(
    node =>
      String(node.type) === 'AnimatedView' &&
      Array.isArray(node.props.style) &&
      node.props.style[0]?.width === '100%',
  );
  expect(stableRows).toHaveLength(2);
  expect(
    stableRows.every(row => {
      const motion = row.props.style.find(
        (style: {opacity?: unknown; transform?: unknown}) =>
          style?.opacity !== undefined && style?.transform !== undefined,
      );
      return (
        motion.opacity.value === 1 && motion.transform[0].translateY.value === 0
      );
    }),
  ).toBe(true);
});

test('makes the send circle visually enabled only for a sendable draft', async () => {
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  const send = () =>
    renderer.root.find(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityLabel === 'Send message',
    );
  expect(JSON.stringify(send().props.style({pressed: false}))).not.toContain(
    '"backgroundColor":"#ffffff","opacity":1',
  );
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Sendable');
  });
  expect(JSON.stringify(send().props.style({pressed: false}))).toContain(
    '"backgroundColor":"#ffffff","opacity":1',
  );
});

test('uses opacity-only entrance motion for a new message when motion is reduced', async () => {
  mockReduceMotion = true;
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: chatMessage(body.id, body.text, 'human', null),
          generation: {id: 'reduced-generation'},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  mockBackend.generationEvents.mockImplementation(() => new Promise(() => {}));
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Reduced motion message');
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
    await Promise.resolve();
  });
  const newRow = renderer.root.find(
    node =>
      String(node.type) === 'AnimatedView' &&
      Array.isArray(node.props.style) &&
      node.props.style[0]?.width === '100%',
  );
  const motion = newRow.props.style.find(
    (style: {opacity?: unknown; transform?: unknown}) =>
      style?.opacity !== undefined && style?.transform !== undefined,
  );
  expect(motion.opacity.value).toBe(0);
  expect(motion.transform[0].translateY.value).toBe(0);
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 1, toValue: 1}),
  );
});

test('offers durable stop while a rewritten-backend generation is active', async () => {
  let finishGeneration!: (value: MockResponse) => void;
  mockBackend.generationEvents.mockImplementation(
    () =>
      new Promise(resolve => {
        finishGeneration = resolve;
      }),
  );
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: {
            id: body.id,
            text: body.text,
            sender: 'human',
            createdAt: body.at,
            generationOutcome: null,
          },
          generation: {id: 'generation-stop'},
        }),
      };
    }
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: '{"messages":[],"page":{"olderCursor":null,"hasOlder":false}}',
      };
    }
    return {
      id: request.id,
      status: 200,
      body: request.path.startsWith('/v1/conversations')
        ? '[]'
        : JSON.stringify({
            contractVersion: '1.0.0',
            items: [],
            window: {
              status: 'complete',
              complete: true,
              hasMore: false,
              nextCursor: null,
            },
            completeness: {
              version:
                request.path === '/v1/tasks'
                  ? 'tasks-completeness-v1'
                  : 'recall-completeness-v1',
              status: 'complete',
              reasons: [],
            },
            absence: null,
          }),
    };
  });
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Stop this');
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const stop = renderer.root.find(
    node => node.props.accessibilityLabel === 'Stop response',
  );
  await ReactTestRenderer.act(async () => {
    await stop.props.onPress();
  });
  expect(mockBackend.cancelGenerationEvents).toHaveBeenCalledWith(
    'generation-stop',
  );
  await ReactTestRenderer.act(async () => {
    finishGeneration({
      id: 'generation-stop',
      status: 200,
      body: 'event: cancelled\nid: terminal\ndata: {"kind":"cancelled","message":null}\n\n',
    });
    await Promise.resolve();
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Stop response',
    ),
  ).toHaveLength(0);
});

test('renders a local echo immediately and replaces it in place canonically', async () => {
  let finishGeneration!: (value: MockResponse) => void;
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: {
            id: body.id,
            text: 'Canonical human',
            sender: 'human',
            createdAt: body.at,
            generationOutcome: null,
          },
          generation: {id: 'generation-echo'},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  mockBackend.generationEvents.mockImplementation(
    () =>
      new Promise(resolve => {
        finishGeneration = resolve;
      }),
  );
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Local echo');
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
    await Promise.resolve();
  });
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'Text' && node.props.children === 'Local echo',
    ),
  ).toHaveLength(1);
  expect(mockChatScrollToEnd).toHaveBeenCalledWith({animated: true});
  mockChatScrollToEnd.mockClear();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Chat scroll region')
      .props.onScroll({
        nativeEvent: {
          contentOffset: {y: 0},
          contentSize: {height: 1200},
          layoutMeasurement: {height: 500},
        },
      });
  });

  await ReactTestRenderer.act(async () => {
    finishGeneration({
      id: 'generation-echo',
      status: 200,
      body: 'event: done\nid: terminal\ndata: {"kind":"done","message":{"id":"assistant-echo","text":"Canonical assistant","sender":"ai","createdAt":2,"generationOutcome":"completed"}}\n\n',
    });
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(mockChatScrollToEnd).not.toHaveBeenCalled();
  const text = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .map(node => node.props.children);
  expect(text).not.toContain('Local echo');
  expect(text.indexOf('Canonical human')).toBeLessThan(
    text.indexOf('Canonical assistant'),
  );
});

test('loads older chat pages once in server order', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          messages: [chatMessage('new-a'), chatMessage('new-b')],
          page: {olderCursor: 'older-page', hasOlder: true},
        }),
      };
    }
    if (request.path.includes('olderCursor=older-page')) {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          messages: [
            chatMessage('old-a'),
            chatMessage('old-b'),
            chatMessage('new-a'),
          ],
          page: {olderCursor: null, hasOlder: false},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Load older messages')
      .props.onPress();
  });
  const text = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .map(node => node.props.children);
  expect(text.filter(value => value === 'new-a')).toHaveLength(1);
  expect(
    ['old-a', 'old-b', 'new-a', 'new-b'].map(value => text.indexOf(value)),
  ).toEqual(
    [
      ...['old-a', 'old-b', 'new-a', 'new-b'].map(value => text.indexOf(value)),
    ].sort((left, right) => left - right),
  );
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('retains and visibly distinguishes a cancelled assistant response', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: chatMessage(body.id, body.text, 'human', null),
          generation: {id: 'generation-cancelled'},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  mockBackend.generationEvents.mockResolvedValue({
    id: 'generation-cancelled',
    status: 200,
    body: 'event: cancelled\nid: terminal\ndata: {"kind":"cancelled","message":{"id":"assistant-cancelled","text":"Retained partial","sender":"ai","createdAt":2,"generationOutcome":"cancelled"}}\n\n',
  });
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Stop later');
  });
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
  });
  const partial = renderer.root.find(
    node =>
      String(node.type) === 'Text' &&
      node.props.children === 'Retained partial',
  );
  expect(partial).toBeDefined();
  expect(
    renderer.root.findAll(
      node =>
        String(node.type) === 'View' &&
        Array.isArray(node.props.style) &&
        node.props.style.some(
          (style: {opacity?: number}) => style?.opacity === 0.72,
        ),
    ),
  ).not.toHaveLength(0);
  expect(JSON.stringify(renderer.toJSON())).toContain('Response stopped');
});

test('refreshes expired older history while retaining a pending local echo', async () => {
  let newestLoads = 0;
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: chatMessage(body.id, 'Canonical pending', 'human', null),
          generation: {id: 'generation-pending'},
        }),
      };
    }
    if (request.path === '/v1/chat-messages?limit=50') {
      newestLoads += 1;
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          messages: [
            chatMessage(
              newestLoads === 1 ? 'stale newest' : 'refreshed newest',
            ),
          ],
          page:
            newestLoads === 1
              ? {olderCursor: 'expired', hasOlder: true}
              : {olderCursor: null, hasOlder: false},
        }),
      };
    }
    if (request.path.includes('olderCursor=expired')) {
      return {
        id: request.id,
        status: 410,
        body: '{"error":{"code":"cursor_expired","retryable":false,"action":"refresh_history"}}',
      };
    }
    return mockBackendResponse(request);
  });
  mockBackend.generationEvents.mockImplementation(() => new Promise(() => {}));
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Pending local');
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
    await Promise.resolve();
  });
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Load older messages')
      .props.onPress();
  });
  const text = renderer.root
    .findAll(node => String(node.type) === 'Text')
    .map(node => node.props.children);
  expect(text).toContain('Pending local');
  expect(text).toContain('refreshed newest');
  expect(text).not.toContain('stale newest');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load older messages',
    ),
  ).toHaveLength(0);
});

test('retains the canonical human and renders a failed assistant delivery', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.method === 'POST') {
      const body = JSON.parse(request.body ?? '');
      return {
        id: request.id,
        status: 201,
        body: JSON.stringify({
          message: chatMessage(body.id, 'Canonical question', 'human', null),
          generation: {id: 'generation-failed'},
        }),
      };
    }
    return mockBackendResponse(request);
  });
  mockBackend.generationEvents.mockResolvedValue({
    id: 'generation-failed',
    status: 200,
    body: 'event: failed\nid: terminal\ndata: {"kind":"failed","error":{"code":"provider_failed","retryable":true}}\n\n',
  });
  const renderer = await renderApp();
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Chat')
      .props.onPress();
  });
  await ReactTestRenderer.act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.onChangeText('Local question');
  });
  await ReactTestRenderer.act(async () => {
    await renderer.root
      .find(node => node.props.accessibilityLabel === 'Send message')
      .props.onPress();
  });
  const rendered = JSON.stringify(renderer.toJSON());
  expect(rendered).toContain('Canonical question');
  expect(rendered).toContain('Response failed. Try again.');
  expect(rendered).not.toContain('Message not sent');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Failed response',
    ),
  ).not.toHaveLength(0);
});
