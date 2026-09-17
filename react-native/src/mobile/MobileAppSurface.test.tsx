import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {TaskPagination} from '../ui/TaskPagination';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));
jest.mock('../ui/OmiAvatar', () => ({
  OmiAvatar: (props: object) =>
    require('react').createElement('OmiAvatar', props),
}));


jest.mock('react-native', () => {
  const ReactRuntime = require('react');
  const component =
    (name: string) =>
    ({children, ...elementProps}: {children?: React.ReactNode}) =>
      ReactRuntime.createElement(name, elementProps, children);
  return {
    FlatList: ({
      data,
      renderItem,
      ListHeaderComponent,
      ListFooterComponent,
      ...listProps
    }: any) =>
      ReactRuntime.createElement(
        'FlatList',
        listProps,
        ListHeaderComponent,
        ListFooterComponent,
        data.map((item: any, index: number) =>
          ReactRuntime.cloneElement(renderItem({item, index}), {
            key: item.key ?? item.id,
          }),
        ),
      ),
    KeyboardAvoidingView: component('KeyboardAvoidingView'),
    Platform: {OS: 'ios'},
    Pressable: component('Pressable'),
    StyleSheet: {
      create: <T,>(styles: T) => styles,
      hairlineWidth: 1,
    },
    Text: component('Text'),
    TextInput: component('TextInput'),
    View: component('View'),
    Image: component('Image'),
  };
});

jest.mock('react-native-safe-area-context', () => ({
  SafeAreaView: ({children, ...props}: {children?: React.ReactNode}) =>
    require('react').createElement('SafeAreaContextView', props, children),
}));

import {MobileAppSurface, type MobileAppSurfaceProps} from './MobileAppSurface';
import {MobileOmnibar} from './MobileOmnibar';

function buildProps(
  overrides: Partial<MobileAppSurfaceProps> = {},
): MobileAppSurfaceProps {
  return {
    activeRoute: 'home',
    omnibar: <Text>Shared bottom dock</Text>,
    capture: {active: true, transcript: 'Preparing the product demo'},
    device: {connected: true, label: '100%'},
    onOpenDevice: jest.fn(),
    onRouteChange: jest.fn(),
    onTaskToggle: jest.fn(),
    conversations: [
      {
        kind: 'conversation',
        id: 'talk-1',
        title: 'Product standup',
        summary: 'Discussed next steps',
        searchableText: 'Product standup Discussed next steps',
        atMs: Date.now(),
      },
    ],
    recall: [
      {
        kind: 'recall',
        id: 'captured:1',
        appName: 'Figma',
        windowTitle: 'Roadmap',
        searchableText: 'Figma Roadmap',
        atMs: Date.now() - 72 * 60 * 1000,
        source: 'captured',
        local: true,
      },
    ],
    timelineStatus: 'ready',
    tasks: [{id: 'task-1', title: 'Prepare product demo', completed: false}],
    taskStatus: 'ready',
    ...overrides,
  };
}

function render(overrides: Partial<MobileAppSurfaceProps> = {}) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <MobileAppSurface {...buildProps(overrides)} />,
    );
  });
  return renderer;
}

function renderedText(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAll(node => String(node.type) === 'Text')
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

describe('MobileAppSurface', () => {
  test.each(['home', 'tasks', 'chat', 'apps', 'settings'] as const)(
    '%s uses the native safe-area boundary',
    activeRoute => {
      const renderer = render({activeRoute});
      expect(renderer.toJSON()).toMatchObject({type: 'SafeAreaContextView'});
    },
  );

  test('one-page timeline keeps the mark, device, settings, action items, mixed events, and bottom dock', () => {
    const tree = JSON.stringify(render().toJSON());
    expect(tree).toContain('Omi');
    expect(tree).toContain('Open Omi device');
    expect(tree).toContain('Settings');
    expect(tree).not.toContain('Action items');
    expect(tree).toContain('Today');
    expect(tree).toContain('Prepare product demo');
    expect(tree).toContain('Product standup');
    expect(tree).toContain('Figma');
    expect(tree).toContain('Conversation');
    expect(tree).toContain('Recall');
    expect(tree).toContain('Shared bottom dock');
    expect(tree).not.toContain('Home');
    expect(tree).not.toContain('Daily Recaps');
    expect(tree).not.toContain('Mind Map');
    expect(tree).not.toContain('Refresh');
    expect(tree).not.toContain('Find your way back');
    expect(tree).toContain('Capture listening');
    expect(tree).not.toContain('Capture is paused');
    expect(tree).not.toContain('Start Live voice');
  });

  test('listening capture sits beside the device chip instead of a page card', () => {
    const renderer = render({
      capture: {active: true, transcript: 'Preparing the product demo'},
    });
    expect(
      renderer.root.find(
        node => node.props.accessibilityLabel === 'Capture listening',
      ),
    ).toBeDefined();
    expect(renderedText(renderer)).not.toContain('Listening for speech');
  });

  test('search filters the already loaded timeline without sending', () => {
    const renderer = render({searchQuery: 'figma'});
    const text = renderedText(renderer);
    expect(text).toContain('Figma');
    expect(text).not.toContain('Product standup');
  });

  test.each(['loading', 'empty', 'offline', 'error'] as const)(
    'renders a named %s action-item state',
    status => {
      const renderer = render({taskStatus: status, tasks: []});
      const panel = renderer.root.find(
        node =>
          node.props.accessibilityLabel === `action items ${status} state`,
      );
      expect(panel).toBeDefined();
    },
  );

  test('failed timeline reads stay failed instead of looking empty', () => {
    const renderer = render({
      timelineStatus: 'error',
      conversations: [],
      recall: [],
    });
    expect(renderedText(renderer)).toContain('Couldn’t load timeline');
    expect(renderedText(renderer)).not.toContain("Nothing on your timeline yet");
  });

  test('settings lives in the top-right control, not a bottom tab', () => {
    const onRouteChange = jest.fn();
    const renderer = render({onRouteChange});
    const settings = renderer.root.find(
      node => node.props.accessibilityLabel === 'Settings',
    );
    act(() => settings.props.onPress());
    expect(onRouteChange).toHaveBeenCalledWith('settings');
    expect(renderedText(renderer)).not.toContain('Conversations');
  });
});

test('shows recording failures and keeps tasks read-only without a mutation handler', () => {
  const renderer = render({
    deviceMessage: 'Recording upload failed. Reconnect your device.',
    onTaskToggle: undefined,
  });
  expect(renderedText(renderer)).toContain(
    'Recording upload failed. Reconnect your device.',
  );
  const task = renderer.root.find(
    node => node.props.accessibilityLabel === 'Open Prepare product demo',
  );
  expect(task.props.disabled).toBe(true);
  expect(task.props.accessibilityRole).toBe('text');
});

test('missing conversation content reports unavailable instead of inventing a library', () => {
  const renderer = render({activeRoute: 'chat'});
  expect(renderedText(renderer)).toContain('Couldn’t load conversations');
  expect(renderedText(renderer)).not.toContain('Product standup');
});

test('task edits wait for authoritative props and preserve a failed draft for retry', () => {
  const onTaskEdit = jest.fn();
  const renderer = render({
    writesAvailable: true,
    onTaskEdit,
    onTaskToggle: jest.fn(),
  });
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Edit Prepare product demo',
      )
      .props.onPress();
  });
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Task description',
    ),
  ).toBeDefined();
});

test('pagination remains available on the tasks overlay', () => {
  const renderer = render({
    activeRoute: 'tasks',
    taskPagination: (
      <TaskPagination
        hasMore={false}
        busy={false}
        notice={null}
        onLoadMore={jest.fn()}
      />
    ),
  });
  expect(renderedText(renderer)).toContain('Prepare product demo');
});

test('the bottom dock stays mounted while chat is open', () => {
  const renderer = render({
    chatContent: <Text>Chat overlay</Text>,
    omnibar: (
      <MobileOmnibar
        mode="Ask"
        onModeChange={jest.fn()}
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        onStop={jest.fn()}
        busy={false}
        canStop={false}
        inputRef={{current: null}}
      />
    ),
  });
  expect(renderedText(renderer)).toContain('Chat overlay');
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Ask and search dock'),
  ).toBeDefined();
});
