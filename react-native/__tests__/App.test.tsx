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
let mockDesktopSearchListener: (() => void) | undefined;
const mockSearchFocus = jest.fn();
type MockRequest = {body?: string; id: string; method: string; path: string};
type MockResponse = {body: string | null; id: string; status: number};
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

jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...props}: {children?: React.ReactNode}) =>
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
    Platform: {OS: 'macos'},
    Pressable: component('Pressable'),
    SafeAreaView: component('SafeAreaView'),
    ScrollView: component('ScrollView'),
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
  expect(output).toContain('Search conversations and memories');
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

test('keeps Home limited to chronological conversations and memories', async () => {
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
                updatedAt: Date.parse('2026-08-08T09:00:00.000Z'),
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
  const output = JSON.stringify(renderer.toJSON());
  expect(output.indexOf('Newer memory')).toBeLessThan(
    output.indexOf('Older conversation'),
  );
  expect(output).not.toContain('Search conversations, memories, and tasks');
  const filters = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'button' &&
        node.props.accessibilityLabel === undefined,
    )
    .map(node => node.props.children.props?.children)
    .filter(Boolean);
  expect(filters).toEqual(['All', 'Conversations', 'Memories']);
  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  expect(search.props.autoFocus).toBe(true);
  await ReactTestRenderer.act(async () => search.props.onChangeText('missing'));
  expect(JSON.stringify(renderer.toJSON())).toContain('No results');
  const clear = renderer.root.find(
    node => node.props.accessibilityLabel === 'Clear search',
  );
  await ReactTestRenderer.act(async () => clear.props.onPress());
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Search Home')
      .props.value,
  ).toBe('');
});

test('does not borrow Home active navigation semantics for Chat', async () => {
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
  expect(
    tabs.every(tab => tab.props.accessibilityState.selected === false),
  ).toBe(true);
  expect(
    tabs.every(tab => tab.props.children[0].props.accessible === false),
  ).toBe(true);
  const pill = renderer.root.find(
    node =>
      String(node.type) === 'AnimatedView' &&
      node.props.accessibilityElementsHidden === true,
  );
  expect(pill.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0})]),
  );
});

test('routes the native macOS search command to Home and focuses search', async () => {
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

test('shows a visible focus ring for keyboard-focused controls and search', async () => {
  const renderer = await renderApp();
  const home = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  )[0];
  await ReactTestRenderer.act(async () => home.props.onFocus({}));
  expect(home.props.style({pressed: false})).toEqual(
    expect.arrayContaining([expect.objectContaining({borderWidth: 2})]),
  );

  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search Home',
  );
  await ReactTestRenderer.act(async () => search.props.onFocus());
  const searchBox = search.parent!;
  expect(searchBox.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({borderWidth: 2})]),
  );
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
  expect(rendered).toContain('Provenance · quiet-river-lantern · synthesis-v1');
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

  await ReactTestRenderer.act(async () => {
    finishGeneration({
      id: 'generation-echo',
      status: 200,
      body: 'event: done\nid: terminal\ndata: {"kind":"done","message":{"id":"assistant-echo","text":"Canonical assistant","sender":"ai","createdAt":2,"generationOutcome":"completed"}}\n\n',
    });
    await Promise.resolve();
    await Promise.resolve();
  });
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
  expect(partial.props.style).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.72})]),
  );
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
