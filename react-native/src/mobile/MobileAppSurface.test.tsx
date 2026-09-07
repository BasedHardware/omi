import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {TaskPagination} from '../ui/TaskPagination';

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
      ListEmptyComponent,
      ...listProps
    }: any) =>
      ReactRuntime.createElement(
        'FlatList',
        listProps,
        ListHeaderComponent,
        ListFooterComponent,
        data.length === 0
          ? ListEmptyComponent
          : data.map((item: any, index: number) =>
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

function buildProps(
  overrides: Partial<MobileAppSurfaceProps> = {},
): MobileAppSurfaceProps {
  return {
    activeRoute: 'home',
    askValue: '',
    capture: {active: true, transcript: 'Preparing the product demo'},
    device: {connected: true, label: '100%'},
    mindMapStatus: 'ready',
    onAskChange: jest.fn(),
    onAskSubmit: jest.fn(),
    onExpandMindMap: jest.fn(),
    onOpenCalls: jest.fn(),
    onOpenDevice: jest.fn(),
    onOpenSettings: jest.fn(),
    onRouteChange: jest.fn(),
    onTaskToggle: jest.fn(),
    onViewRecaps: jest.fn(),
    onViewTasks: jest.fn(),
    recaps: [
      {id: 'recap-1', title: 'Omi gets simpler', dateLabel: 'Yesterday'},
    ],
    recapStatus: 'ready',
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

test('an unavailable write door disables Ask instead of leaving it sendable', () => {
  const onAskSubmit = jest.fn();
  const renderer = render({askUnavailable: true, onAskSubmit});
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Send to Omi unavailable',
  );
  expect(send.props.disabled).toBe(true);
  send.props.onPress();
  expect(onAskSubmit).not.toHaveBeenCalled();
  const ask = renderer.root.find(
    node => node.props.accessibilityLabel === 'Ask Omi',
  );
  expect(ask.props.editable).toBe(false);
  expect(ask.props.onSubmitEditing).toBeUndefined();
});

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
    expect(tree).toContain('Tasks');
    expect(tree).toContain('Prepare product demo');
    expect(tree).toContain('Daily Recaps');
    expect(tree).toContain('Omi gets simpler');
    expect(tree).toContain('Mind Map');
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
    ['apps', 'Couldn’t load apps'],
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

test('missing apps content reports unavailable instead of an empty catalogue', () => {
  const renderer = render({activeRoute: 'apps'});
  expect(renderedText(renderer)).toContain('Couldn’t load apps');
  expect(renderedText(renderer)).not.toContain('No apps connected yet');
});

test('mounted apps content is not replaced by an empty catalogue', () => {
  const renderer = render({
    activeRoute: 'apps',
    appsContent: <Text>Catalogue loaded</Text>,
  });
  expect(renderedText(renderer)).toContain('Catalogue loaded');
  expect(renderedText(renderer)).not.toContain('Couldn’t load apps');
  expect(renderedText(renderer)).not.toContain('No apps connected yet');
});

test('empty Daily Recaps keep the complete-library copy by default', () => {
  const renderer = render({recaps: []});
  expect(renderedText(renderer)).toContain('No recaps yet');
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'recaps empty state',
    ),
  ).toBeDefined();
});

test('empty Daily Recaps keep incomplete conversation coverage instead of claiming emptiness', () => {
  const renderer = render({
    recaps: [],
    recapEmptyCopy: 'Recaps are incomplete.',
  });
  expect(renderedText(renderer)).toContain('Recaps are incomplete.');
  expect(renderedText(renderer)).not.toContain('No recaps yet');
});

test('loaded Daily Recaps keep incomplete coverage instead of looking complete', () => {
  const renderer = render({
    recapCoverageCopy: 'Recaps are incomplete.',
  });
  expect(renderedText(renderer)).toContain('Omi gets simpler');
  expect(renderedText(renderer)).toContain('Recaps are incomplete.');
  expect(renderedText(renderer)).not.toContain('No recaps yet');
});

test('loaded Daily Recaps omit more-available after a closed later page', () => {
  const renderer = render({
    recapCoverageCopy: null,
  });
  expect(renderedText(renderer)).toContain('Omi gets simpler');
  expect(renderedText(renderer)).not.toContain('More recaps are available.');
});

test('loaded Home tasks keep more-available coverage instead of looking complete', () => {
  const renderer = render({
    taskCoverageCopy: 'More tasks are available.',
  });
  expect(renderedText(renderer)).toContain('Prepare product demo');
  expect(renderedText(renderer)).toContain('More tasks are available.');
});

test('loaded Home tasks omit more-available after a closed later page', () => {
  const renderer = render({
    taskCoverageCopy: null,
  });
  expect(renderedText(renderer)).toContain('Prepare product demo');
  expect(renderedText(renderer)).not.toContain('More tasks are available.');
});

test('loaded Tasks tab omit more-available after a closed later page', () => {
  const renderer = render({
    activeRoute: 'tasks',
    taskCoverageCopy: null,
  });
  expect(renderedText(renderer)).toContain('Prepare product demo');
  expect(renderedText(renderer)).not.toContain('More tasks are available.');
});

test('loaded Tasks tab keep more-available coverage instead of looking complete', () => {
  const renderer = render({
    activeRoute: 'tasks',
    taskCoverageCopy: 'More tasks are available.',
  });
  expect(renderedText(renderer)).toContain('Prepare product demo');
  expect(renderedText(renderer)).toContain('More tasks are available.');
});

test('nested non-retryable recap errors use unavailable copy instead of a load blip', () => {
  const renderer = render({
    recaps: [],
    recapStatus: 'error',
    recapErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
  });
  expect(renderedText(renderer)).toContain(
    'This saved data is not available from the selected Omi service yet.',
  );
  expect(renderedText(renderer)).not.toContain('Couldn’t load recaps');
});

test('nested non-retryable Home task errors use unavailable copy instead of a load blip', () => {
  const renderer = render({
    tasks: [],
    taskStatus: 'error',
    taskErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
    onRefresh: jest.fn(),
  });
  expect(renderedText(renderer)).toContain(
    'This saved data is not available from the selected Omi service yet.',
  );
  expect(renderedText(renderer)).not.toContain('Couldn’t load tasks');
  expect(renderedText(renderer)).not.toContain(
    'Task editing is unavailable for this connection.',
  );
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh tasks',
    ),
  ).toHaveLength(0);
});

test('retryable Home task errors still offer Refresh', () => {
  const onRefresh = jest.fn();
  const renderer = render({
    tasks: [],
    taskStatus: 'error',
    taskErrorCopy:
      'This saved data could not be loaded. Retry without changing it.',
    onRefresh,
  });
  const refresh = renderer.root.find(
    node => node.props.accessibilityLabel === 'Refresh tasks',
  );
  act(() => refresh.props.onPress());
  expect(onRefresh).toHaveBeenCalledTimes(1);
});

test('nested non-retryable Tasks tab errors omit Refresh', () => {
  const renderer = render({
    activeRoute: 'tasks',
    tasks: [],
    taskStatus: 'error',
    taskErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh tasks',
    ),
  ).toHaveLength(0);
});

test('retryable Tasks tab errors still offer Refresh', () => {
  const renderer = render({
    activeRoute: 'tasks',
    tasks: [],
    taskStatus: 'error',
    taskErrorCopy:
      'This saved data could not be loaded. Retry without changing it.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh tasks',
    ).length,
  ).toBeGreaterThan(0);
});

test('nested non-retryable recap errors omit Refresh', () => {
  const renderer = render({
    recaps: [],
    recapStatus: 'error',
    recapErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh recaps',
    ),
  ).toHaveLength(0);
});

test('retryable recap errors still offer Refresh', () => {
  const renderer = render({
    recaps: [],
    recapStatus: 'error',
    recapErrorCopy:
      'This saved data could not be loaded. Retry without changing it.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh recaps',
    ).length,
  ).toBeGreaterThan(0);
});

test('nested non-retryable mind map errors omit Refresh', () => {
  const renderer = render({
    mindMapStatus: 'error',
    mindMapErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh mind map',
    ),
  ).toHaveLength(0);
});

test('retryable mind map errors still offer Refresh', () => {
  const renderer = render({
    mindMapStatus: 'error',
    mindMapErrorCopy:
      'This saved data could not be loaded. Retry without changing it.',
    onRefresh: jest.fn(),
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh mind map',
    ).length,
  ).toBeGreaterThan(0);
});

test('missing settings content does not offer Refresh', () => {
  const renderer = render({
    activeRoute: 'settings',
    onRefresh: jest.fn(),
  });
  expect(renderedText(renderer)).toContain('Couldn’t load settings');
  expect(
    renderer.root.findAll(node =>
      String(node.props.accessibilityLabel ?? '').startsWith('Refresh '),
    ),
  ).toHaveLength(0);
});

test('Home does not claim task editing unavailable while tasks are loading', () => {
  const renderer = render({tasks: [], taskStatus: 'loading'});
  expect(renderedText(renderer)).not.toContain(
    'Task editing is unavailable for this connection.',
  );
});

test('Home reports a closed task-write door after tasks load', () => {
  const renderer = render({writesAvailable: false});
  expect(renderedText(renderer)).toContain(
    'Task editing is unavailable for this connection.',
  );
});

test('nested non-retryable mind map errors use unavailable copy instead of a load blip', () => {
  const renderer = render({
    mindMapStatus: 'error',
    mindMapErrorCopy:
      'This saved data is not available from the selected Omi service yet.',
  });
  expect(renderedText(renderer)).toContain(
    'This saved data is not available from the selected Omi service yet.',
  );
  expect(renderedText(renderer)).not.toContain('Couldn’t load mind map');
});

test('empty Home tasks keep the complete-library copy by default', () => {
  const renderer = render({tasks: []});
  expect(renderedText(renderer)).toContain("Nothing's waiting on you.");
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'tasks empty state',
    ),
  ).toBeDefined();
});

test('empty Home tasks keep incomplete coverage instead of claiming emptiness', () => {
  const renderer = render({
    tasks: [],
    taskEmptyCopy: 'Tasks are incomplete.',
  });
  expect(renderedText(renderer)).toContain('Tasks are incomplete.');
  expect(renderedText(renderer)).not.toContain("Nothing's waiting on you.");
});

test('empty Tasks tab keeps incomplete coverage instead of claiming emptiness', () => {
  const renderer = render({
    activeRoute: 'tasks',
    tasks: [],
    taskEmptyCopy: 'Tasks are incomplete.',
  });
  expect(renderedText(renderer)).toContain('Tasks are incomplete.');
  expect(renderedText(renderer)).not.toContain("Nothing's waiting on you.");
});

test('untitled processing recaps stay visible instead of rendering a blank card', () => {
  const renderer = render({
    recaps: [
      {
        id: 'recap-processing',
        title: 'Processing conversation…',
        dateLabel: 'Monday',
      },
    ],
  });
  expect(renderedText(renderer)).toContain('Processing conversation…');
  expect(renderedText(renderer)).not.toContain('No recaps yet');
});

test('missing settings content reports unavailable instead of a blank settings stage', () => {
  const renderer = render({activeRoute: 'settings'});
  expect(renderedText(renderer)).toContain('Couldn’t load settings');
});

test('mounted settings content is not replaced by a blank settings stage', () => {
  const renderer = render({
    activeRoute: 'settings',
    settingsContent: <Text>Account settings loaded</Text>,
  });
  expect(renderedText(renderer)).toContain('Account settings loaded');
  expect(renderedText(renderer)).not.toContain('Couldn’t load settings');
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
        tasks={[{id: 'task-1', title: 'Updated task', completed: true}]}
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
