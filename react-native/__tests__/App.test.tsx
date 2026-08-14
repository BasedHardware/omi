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
  const parallel = jest.fn((animations: Array<{start: () => void}>) => ({
    start: () => animations.forEach(animation => animation.start()),
  }));
  const FlatList = ({
    data,
    ListEmptyComponent,
    ListHeaderComponent,
    renderItem,
  }: {
    data: unknown[];
    ListEmptyComponent: React.ReactNode;
    ListHeaderComponent: React.ReactNode;
    renderItem: (item: {item: unknown}) => React.ReactNode;
  }) => (
    <View>
      {ListHeaderComponent}
      {data.map((item, index) => (
        <View key={index}>{renderItem({item})}</View>
      ))}
      {data.length === 0 && ListEmptyComponent}
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
      timing,
      Value: MockAnimatedValue,
      View: component('AnimatedView'),
    },
    Easing: {cubic: 'cubic', out: jest.fn(value => value)},
    FlatList,
    KeyboardAvoidingView: component('KeyboardAvoidingView'),
    NativeModules: {},
    Platform: {OS: 'ios'},
    Pressable: component('Pressable'),
    SafeAreaView: component('SafeAreaView'),
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
  'lucide-react-native/icons/mic',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Mic', props),
);
jest.mock(
  'lucide-react-native/icons/paperclip',
  () => (props: Record<string, unknown>) =>
    mockReact.createElement('Paperclip', props),
);

import App from '../App';

beforeEach(() => {
  jest.clearAllMocks();
  mockViewportWidth = 1200;
  mockReduceMotion = false;
  mockReduceMotionListener = undefined;
});

async function renderApp() {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
    await Promise.resolve();
  });
  return renderer!;
}

test('translates the desktop Home resting stage and rail', async () => {
  const renderer = await renderApp();
  const output = JSON.stringify(renderer.toJSON());
  const tabs = renderer.root.findAll(
    node =>
      String(node.type) === 'Pressable' &&
      node.props.accessibilityRole === 'tab',
  );

  expect(output).toContain('I’m ready.');
  expect(output).toContain('CURRENTS');
  expect(output).toContain('Nothing’s waiting on you.');
  expect(output).toContain('Ask anything...');
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
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Send message unavailable',
    ).props.disabled,
  ).toBe(true);
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 250, toValue: 1}),
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
  expect(
    renderer.root.find(node => String(node.type) === 'Paperclip').props.size,
  ).toBe(18);
  expect(
    renderer.root.find(node => String(node.type) === 'Mic').props.size,
  ).toBe(18);
  expect(
    renderer.root.find(node => String(node.type) === 'ArrowUp').props,
  ).toEqual(expect.objectContaining({size: 18, strokeWidth: 2.5}));
});

test('navigates to truthful read-unavailable projections and replays the stage transition', async () => {
  const renderer = await renderApp();
  const destinations = [
    ['Conversations', 'Conversation history is unavailable in this build.'],
    ['Memories', 'Memory history is unavailable in this build.'],
    ['Tasks', 'Task history is unavailable in this build.'],
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
    expect(output).toContain('Nothing to show yet');
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
    expect.objectContaining({duration: 250, toValue: 1}),
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
    renderer.root.find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.multiline,
  ).toBe(true);
  expect(Animated.timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 200, toValue: 1}),
  );
});

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
    tablist.props.style[2].transform[0].translateY.setValue,
  ).toHaveBeenCalledWith(0);
});

test('fills and preserves the ask pill draft from a quick prompt', async () => {
  const renderer = await renderApp();
  const prompt = renderer.root
    .findAll(
      node =>
        String(node.type) === 'Pressable' &&
        node.props.accessibilityRole === 'button',
    )
    .find(
      node => node.props.children.props.children === 'What should I remember?',
    )!;

  await ReactTestRenderer.act(async () => {
    prompt.props.onPress();
  });

  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Ask Omi')
      .props.value,
  ).toBe('What should I remember?');
});
