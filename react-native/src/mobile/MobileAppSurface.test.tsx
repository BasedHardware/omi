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
    onViewConversations: jest.fn(),
    onViewTasks: jest.fn(),
    conversations: [
      {
        id: 'conversation-1',
        title: 'Omi gets simpler',
        summary: 'Make room for the work that matters.',
        createdAt: '2026-09-17T10:00:00Z',
        startedAt: null,
      },
    ],
    conversationStatus: 'ready',
    tasks: [
      {
        id: 'task-1',
        title: 'Prepare product demo',
        completed: false,
        dueAt: Date.parse('2026-09-18T12:00:00Z'),
        owner: 'Sam',
      },
    ],
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
  test.each(['home', 'tasks', 'chat', 'apps'] as const)(
    '%s uses the native safe-area boundary',
    activeRoute => {
      const renderer = render({activeRoute});
      expect(renderer.toJSON()).toMatchObject({type: 'SafeAreaContextView'});
    },
  );
  test('renders the shipping mobile hierarchy from real projections', () => {
    const tree = JSON.stringify(render().toJSON());
    expect(tree).toContain('Listening');
    expect(tree).toContain('Action items');
    expect(tree).toContain('Prepare product demo');
    expect(tree).toContain('Recent conversations');
    expect(tree).toContain('Omi gets simpler');
    expect(tree).toContain('Make room for the work that matters.');
    expect(tree).not.toContain('Mind Map');
    expect(tree).not.toContain('Daily Recaps');
    expect(tree).not.toContain('Saved data unavailable');
    expect(tree).not.toContain('Retry');
  });

  test.each(['loading', 'empty', 'offline', 'error'] as const)(
    'renders a named %s projection state',
    status => {
      const renderer = render({taskStatus: status, tasks: []});
      const panel = renderer.root.find(
        node => node.props.accessibilityLabel === `tasks ${status} state`,
      );
      expect(panel).toBeDefined();
    },
  );

  test('routes and toggles with accessible controls', () => {
    const onRouteChange = jest.fn();
    const onTaskToggle = jest.fn();
    const renderer = render({
      onRouteChange,
      onTaskToggle,
      writesAvailable: true,
    });
    const apps = renderer.root.find(
      node => node.props.accessibilityLabel === 'Apps',
    );
    const task = renderer.root.find(
      node => node.props.accessibilityLabel === 'Complete Prepare product demo',
    );
    act(() => apps.props.onPress());
    act(() => task.props.onPress());
    expect(onRouteChange).toHaveBeenCalledWith('apps');
    expect(onTaskToggle).toHaveBeenCalledWith('task-1');
  });

  test.each([
    ['chat', 'Conversation content'],
    ['tasks', 'Prepare product demo'],
    ['apps', 'No apps connected yet'],
  ] as const)('renders the shipping %s destination', (route, copy) => {
    const tree = renderedText(
      render({
        activeRoute: route,
        conversationContent: <Text>Conversation content</Text>,
      }),
    );
    expect(tree).toContain(copy);
    expect(tree).not.toContain('Saved data unavailable');
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

test('missing conversation content reports unavailable instead of rendering noninteractive recap cards', () => {
  const renderer = render({activeRoute: 'chat'});
  expect(renderedText(renderer)).toContain('Couldn’t load conversations');
  expect(renderedText(renderer)).not.toContain('Omi gets simpler');
  expect(renderedText(renderer)).not.toContain('Your timeline is empty');
});

test('task edits wait for authoritative props and preserve a failed draft for retry', () => {
  const onTaskEdit = jest.fn();
  const onTaskToggle = jest.fn();
  const onRetryTaskMutation = jest.fn();
  const onDismissTaskMutation = jest.fn();
  const props = buildProps({
    activeRoute: 'tasks',
    writesAvailable: true,
    onTaskEdit,
    onTaskToggle,
  });
  const renderer = render(props);
  const control = (label: string) =>
    renderer.root.findAll(node => node.props.accessibilityLabel === label)[0];
  act(() => control('Edit Prepare product demo').props.onPress());
  act(() => control('Task description').props.onChangeText('Updated task'));
  act(() => control('Save task description').props.onPress());
  expect(onTaskEdit).toHaveBeenCalledWith('task-1', 'Updated task');
  expect(control('Task description').props.value).toBe('Updated task');
  expect(
    control('Complete Prepare product demo').props.accessibilityState.checked,
  ).toBe(false);
  act(() =>
    renderer.update(
      <MobileAppSurface
        {...props}
        busyTaskId="task-1"
        taskMutationError="Could not save"
        onRetryTaskMutation={onRetryTaskMutation}
        onDismissTaskMutation={onDismissTaskMutation}
      />,
    ),
  );
  expect(control('Complete Prepare product demo').props.disabled).toBe(true);
  expect(control('Save task description').props.disabled).toBe(true);
  expect(control('Task description').props.value).toBe('Updated task');
  act(() => control('Retry task change').props.onPress());
  act(() => control('Dismiss task change').props.onPress());
  expect(onRetryTaskMutation).toHaveBeenCalledTimes(1);
  expect(onDismissTaskMutation).toHaveBeenCalledTimes(1);
  act(() =>
    renderer.update(
      <MobileAppSurface
        {...props}
        tasks={[{...props.tasks[0], title: 'Updated task', completed: true}]}
      />,
    ),
  );
  expect(control('Reopen Updated task').props.accessibilityState.checked).toBe(
    true,
  );
  act(() => control('Reopen Updated task').props.onPress());
  expect(onTaskToggle).toHaveBeenCalledWith('task-1');
  expect(control('Save task description').props.disabled).toBe(true);
});

test('mobile task footer exposes pending pagination and its action', () => {
  const onLoadMore = jest.fn();
  const renderer = render({
    activeRoute: 'tasks',
    taskPagination: (
      <TaskPagination
        hasMore
        busy={false}
        notice={null}
        onLoadMore={onLoadMore}
      />
    ),
  });
  act(() =>
    renderer.root
      .findAll(node => node.props.accessibilityLabel === 'Load more tasks')[0]!
      .props.onPress(),
  );
  expect(onLoadMore).toHaveBeenCalledTimes(1);
  act(() =>
    renderer.update(
      <MobileAppSurface
        {...buildProps({
          activeRoute: 'tasks',
          taskPagination: (
            <TaskPagination
              hasMore
              busy
              notice="Try again"
              onLoadMore={onLoadMore}
            />
          ),
        })}
      />,
    ),
  );
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more tasks',
    )[0]!.props.disabled,
  ).toBe(true);
  expect(renderedText(renderer)).toContain('Try again');
  act(() => renderer.unmount());
});

test('mobile waiting-for-audio state never claims Listening before the first packet', () => {
  const renderer = render({
    capture: {active: true, waitingForAudio: true, transcript: ''},
  });
  expect(renderedText(renderer)).toContain('Waiting for audio');
  expect(renderedText(renderer)).not.toContain('Listening');
  act(() =>
    renderer.update(
      <MobileAppSurface
        {...buildProps({
          capture: {active: true, waitingForAudio: false, transcript: ''},
        })}
      />,
    ),
  );
  expect(renderedText(renderer)).toContain('Listening');
  expect(renderedText(renderer)).not.toContain('Waiting for audio');
  act(() => renderer.unmount());
});

test('the mobile composer rejects blank taps and keyboard submits but accepts a draft', () => {
  const onAskSubmit = jest.fn();
  const omnibar = (value: string) => (
    <MobileOmnibar
      mode="Ask"
      onModeChange={jest.fn()}
      value={value}
      onChange={jest.fn()}
      onSubmit={onAskSubmit}
      onStop={jest.fn()}
      busy={false}
      canStop={false}
      inputRef={{current: null}}
    />
  );
  const props = buildProps({omnibar: omnibar('  \n ')});
  const renderer = render(props);
  const control = (label: string) =>
    renderer.root.findAll(node => node.props.accessibilityLabel === label)[0];
  expect(control('Send to Omi').props.disabled).toBe(true);
  act(() => control('Send to Omi').props.onPress());
  act(() => control('Ask Omi').props.onSubmitEditing());
  expect(onAskSubmit).not.toHaveBeenCalled();
  act(() =>
    renderer.update(
      <MobileAppSurface
        {...props}
        omnibar={omnibar('What did I decide today?')}
      />,
    ),
  );
  expect(control('Send to Omi').props.disabled).toBe(false);
  act(() => control('Send to Omi').props.onPress());
  act(() => control('Ask Omi').props.onSubmitEditing());
  expect(onAskSubmit).toHaveBeenCalledTimes(2);
  act(() => renderer.unmount());
});

test('the mobile mark respects reduced motion and does not pretend to be a capture control', () => {
  const props = buildProps({capture: {active: false, transcript: ''}});
  const renderer = render(props);
  const mark = () => renderer.root.findByType('OmiAvatar' as any);
  expect(mark().props.reduceMotion).toBe(true);
  expect(mark().props.motion).toBe('breathe');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Say hello to Omi',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Open calls',
    ),
  ).toHaveLength(0);
  expect(props.onRouteChange).not.toHaveBeenCalled();
  expect(props.onOpenDevice).not.toHaveBeenCalled();
  expect(renderedText(renderer)).not.toContain('Capture is paused');
  act(() => renderer.unmount());
});

test('Home shows open task metadata and opens all tasks without a Tasks tab', () => {
  const props = buildProps();
  const tasks = [
    {...props.tasks[0], id: 'done', title: 'Already finished', completed: true},
    props.tasks[0],
    {
      ...props.tasks[0],
      id: 'no-date',
      title: 'Unscheduled idea',
      dueAt: null,
      owner: null,
    },
  ];
  const tree = render({...props, tasks});
  const text = renderedText(tree);
  expect(text).toContain('Due Sep 18 · Sam');
  expect(text).toContain('Unscheduled idea');
  expect(text).not.toContain('Already finished');
  expect(text).not.toContain('No due date');
  expect(text).not.toContain('Invalid Date');
  expect(
    tree.root.findAll(
      node =>
        node.props.accessibilityRole === 'tab' &&
        node.props.accessibilityLabel === 'Tasks',
    ),
  ).toHaveLength(0);
  act(() =>
    tree.root
      .findAll(
        node => node.props.accessibilityLabel === 'See all action items',
      )[0]
      .props.onPress(),
  );
  expect(props.onViewTasks).toHaveBeenCalledTimes(1);
  act(() =>
    tree.update(
      <MobileAppSurface {...props} tasks={tasks} activeRoute="tasks" />,
    ),
  );
  expect(renderedText(tree)).toContain('Already finished');
  expect(
    tree.root.findAll(node => node.props.accessibilityLabel === 'Home')[0].props
      .accessibilityState.selected,
  ).toBe(true);
  act(() =>
    tree.root
      .findAll(node => node.props.accessibilityLabel === 'Back to Home')[0]
      .props.onPress(),
  );
  expect(props.onRouteChange).toHaveBeenCalledWith('home');
  act(() => tree.unmount());
});
