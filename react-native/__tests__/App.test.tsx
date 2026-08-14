/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import {Animated} from 'react-native';

const mockReact = React;

let mockViewportWidth = 1200;
let mockReduceMotion = false;
let mockReduceMotionListener: ((enabled: boolean) => void) | undefined;
type MockRequest = {body?: string; id: string; method: string; path: string};
type MockResponse = {body: string | null; id: string; status: number};
const mockBackend = {
  cancelGenerationEvents: jest.fn(async (_generationId: string) => undefined),
  generationEvents: jest.fn(
    async (_generationId: string, _lastEventId: string | null) => '',
  ),
  request: jest.fn<Promise<MockResponse>, [MockRequest]>(
    async (_request: MockRequest) => ({
      body: null,
      id: '',
      status: 500,
    }),
  ),
};

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...props}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, props, children);
  const Text = component('Text');
  const View = component('View');
  class MockAnimatedValue {
    value: number;
    setValue = jest.fn((value: number) => {
      this.value = value;
    });

    constructor(value: number) {
      this.value = value;
    }
  }
  const timing = jest.fn(() => ({start: jest.fn()}));
  const spring = jest.fn(() => ({start: jest.fn()}));
  const parallel = jest.fn((animations: Array<{start: () => void}>) => ({
    start: () => animations.forEach(animation => animation.start()),
  }));
  const FlatList = ({
    data,
    ListEmptyComponent,
    ListFooterComponent,
    ListHeaderComponent,
    renderItem,
  }: {
    data: unknown[];
    ListEmptyComponent: React.ReactNode;
    ListFooterComponent: React.ReactNode;
    ListHeaderComponent: React.ReactNode;
    renderItem: (item: {item: unknown}) => React.ReactNode;
  }) => (
    <View>
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
      parallel,
      spring,
      timing,
      Value: MockAnimatedValue,
      View: component('AnimatedView'),
    },
    Easing: {
      bezier: jest.fn((x1, y1, x2, y2) => [x1, y1, x2, y2]),
      cubic: 'cubic',
      out: jest.fn(value => value),
    },
    FlatList,
    KeyboardAvoidingView: component('KeyboardAvoidingView'),
    NativeModules: {},
    Platform: {OS: 'ios'},
    Pressable: component('Pressable'),
    SafeAreaView: component('SafeAreaView'),
    ScrollView: component('ScrollView'),
    StyleSheet: {create: <T,>(styles: T) => styles},
    Text,
    TextInput: component('TextInput'),
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
  omiBackend: {
    cancelGenerationEvents: (generationId: string) =>
      mockBackend.cancelGenerationEvents(generationId),
    generationEvents: (generationId: string, lastEventId: string | null) =>
      mockBackend.generationEvents(generationId, lastEventId),
    request: (request: MockRequest) => mockBackend.request(request),
  },
}));

import App from '../App';

beforeEach(() => {
  jest.clearAllMocks();
  mockViewportWidth = 1200;
  mockReduceMotion = false;
  mockReduceMotionListener = undefined;
  mockBackend.cancelGenerationEvents.mockResolvedValue(undefined);
  mockBackend.generationEvents.mockResolvedValue('');
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {id: request.id, status: 200, body: '{"messages":[]}'};
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
  });
});

async function renderApp() {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });
  return renderer!;
}

test('renders the collapsed reference rail and search-first desktop Home', async () => {
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());
  const tabs = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  );

  expect(output).toContain('Search what you’ve seen and heard');
  expect(output).toContain('Search conversations, memories, and tasks');
  expect(output).toContain('QA bridge check');
  expect(output).toContain('Open Chat');
  expect(output).not.toContain('I’m ready.');
  expect(output).not.toContain('Ask anything...');
  expect(output).not.toContain('Omi connection');
  expect(output).not.toContain('No nearby devices');
  expect(tabs.map(tab => tab.props.children[1].props.children)).toEqual([
    'Home',
    'Conversations',
    'Memories',
    'Tasks',
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

test('navigates to rewritten-backend read projections and replays the stage transition', async () => {
  const renderer = await renderApp();
  const destinations = [
    ['Conversations', 'QA bridge check'],
    ['Memories', 'No memories yet.'],
    ['Tasks', 'No tasks yet.'],
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

test('keeps successful reads visible and reports each unavailable domain', async () => {
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/chat-messages?limit=50') {
      return {id: request.id, status: 200, body: '{"messages":[]}'};
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
  const home = JSON.stringify(renderer.toJSON());
  expect(home).toContain('Keep the successful task');
  expect(home).toContain('desktop-conversations-read failed (503)');
  expect(home).toContain('Tasks are incomplete.');
  expect(home).toContain('pending_writes');

  const conversations = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'tab',
    )
    .find(node => node.props.children[1].props.children === 'Conversations')!;
  await ReactTestRenderer.act(async () => conversations.props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'desktop-conversations-read failed (503)',
  );
});

test('uses a full pane with bottom navigation on mobile', async () => {
  mockViewportWidth = 390;
  const renderer = await renderApp();
  const tablist = renderer.root.find(
    node => node.props.accessibilityRole === 'tablist',
  );

  expect(tablist.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({borderTopWidth: 1})]),
  );
  expect(
    renderer.root.findAll(
      node => String(node.type) === 'Text' && node.props.children === 'omi',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Search Home')
      .props.value,
  ).toBe('');
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 200, toValue: 1}),
  );
});

test('resizes pane and rail at their independent reference breakpoints', async () => {
  mockViewportWidth = 700;
  const tablet = await renderApp();
  const tabletTablist = tablet.root.find(
    node => node.props.accessibilityRole === 'tablist',
  );
  const tabletPane = tablet.root.find(
    node => String(node.type) === 'KeyboardAvoidingView',
  );
  expect(tabletTablist.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({borderTopWidth: 1})]),
  );
  expect(tabletPane.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({borderRadius: 26})]),
  );
  await ReactTestRenderer.act(async () => tablet.unmount());

  mockViewportWidth = 1000;
  const intermediate = await renderApp();
  expect(
    intermediate.root.find(node => node.props.accessibilityRole === 'tablist')
      .props.style,
  ).toEqual(
    expect.arrayContaining([expect.objectContaining({borderTopWidth: 1})]),
  );
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

test('removes translation and shortens fades when reduced motion is enabled', async () => {
  mockViewportWidth = 390;
  mockReduceMotion = true;
  const renderer = await renderApp();

  await ReactTestRenderer.act(async () => {
    mockReduceMotionListener?.(true);
    await Promise.resolve();
  });

  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 1, toValue: 1}),
  );
  const stage = renderer.root.find(
    node => node.props.accessibilityLabel === 'Home stage',
  );
  const tablist = renderer.root.find(
    node => node.props.accessibilityRole === 'tablist',
  );
  expect(
    stage.props.style[1].transform[0].translateY.setValue,
  ).toHaveBeenCalledWith(0);
  expect(
    tablist.props.style.find((style: {transform?: unknown}) => style?.transform)
      .transform[0].translateY.setValue,
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
  const translateY = activePill.props.style[1].transform[0].translateY;
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

test('fills and preserves the ask pill draft from a quick prompt', async () => {
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

  await ReactTestRenderer.act(async () => {
    prompt.props.onPress();
  });

  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.value,
  ).toBe('What should I remember?');
});

test('offers durable stop while a rewritten-backend generation is active', async () => {
  let finishGeneration!: (value: string) => void;
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
      return {id: request.id, status: 200, body: '{"messages":[]}'};
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
    finishGeneration(
      'event: cancelled\nid: terminal\ndata: {"kind":"cancelled","message":null}\n\n',
    );
    await Promise.resolve();
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Stop response',
    ),
  ).toHaveLength(0);
});
