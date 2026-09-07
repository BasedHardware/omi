import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {TasksPage} from './Tasks';
import {TaskPagination} from '../ui/TaskPagination';
import type {TaskMutationProps} from '../ui/TaskEditor';
import type {TaskProjection} from '../desktopReadClient';

const task: TaskProjection = {
  kind: 'task',
  id: 'task-1',
  title: 'Prepare demo',
  summary: '',
  searchableText: '',
  completed: false,
  completedAt: null,
  dueAt: null,
  owner: null,
  source: 'chat',
  provenance: [],
  sortOrder: 0,
  indentLevel: 0,
  createdAt: 1,
  updatedAt: 1,
  revision: null,
};
const outcome = {
  status: 'success' as const,
  value: {
    items: [task],
    page: {
      windowStatus: 'complete' as const,
      complete: true,
      hasMore: false,
      nextCursor: null,
      completenessStatus: 'complete' as const,
      reasons: [],
    },
  },
};

function render(props: TaskMutationProps = {}) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage outcome={outcome} loading={false} {...props} />,
    );
  });
  return renderer;
}
function control(renderer: ReactTestRenderer.ReactTestRenderer, label: string) {
  return renderer.root.findAll(
    node => node.props.accessibilityLabel === label,
  )[0];
}

test('task page remains read-only without write authority', () => {
  const renderer = render({onTaskToggle: jest.fn(), onTaskEdit: jest.fn()});
  expect(control(renderer, 'Open Prepare demo').props.disabled).toBe(true);
  act(() => control(renderer, 'Open task: Prepare demo').props.onPress());
  expect(control(renderer, 'Task description')).toBeUndefined();
});

test('task page edits and toggles only through handlers with pending and error recovery', () => {
  const onTaskToggle = jest.fn();
  const onTaskEdit = jest.fn();
  const onDismissTaskMutation = jest.fn();
  const props = {writesAvailable: true, onTaskToggle, onTaskEdit};
  const renderer = render(props);
  act(() => control(renderer, 'Complete Prepare demo').props.onPress());
  expect(onTaskToggle).toHaveBeenCalledWith('task-1');
  expect(
    control(renderer, 'Complete Prepare demo').props.accessibilityState.checked,
  ).toBe(false);
  act(() => control(renderer, 'Open task: Prepare demo').props.onPress());
  act(() => control(renderer, 'Task description').props.onChangeText(''));
  expect(control(renderer, 'Save task description').props.disabled).toBe(true);
  act(() =>
    control(renderer, 'Task description').props.onChangeText('Revised demo'),
  );
  act(() => control(renderer, 'Save task description').props.onPress());
  expect(onTaskEdit).toHaveBeenCalledWith('task-1', 'Revised demo');
  act(() =>
    renderer.update(
      <TasksPage
        outcome={outcome}
        loading={false}
        {...props}
        busyTaskId="task-1"
        taskMutationError="Tasks changed. Reload before editing."
        onDismissTaskMutation={onDismissTaskMutation}
      />,
    ),
  );
  expect(control(renderer, 'Complete Prepare demo').props.disabled).toBe(true);
  expect(control(renderer, 'Task description').props.value).toBe(
    'Revised demo',
  );
  expect(control(renderer, 'Retry task change')).toBeUndefined();
  act(() => control(renderer, 'Dismiss task change').props.onPress());
  expect(onDismissTaskMutation).toHaveBeenCalledTimes(1);
});

test('task due dates use canonical epoch milliseconds', () => {
  const dueAt = Date.UTC(2026, 8, 8);
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        loading={false}
        outcome={{
          ...outcome,
          value: {...outcome.value, items: [{...task, dueAt}]},
        }}
      />,
    );
  });
  const expected = new Date(dueAt).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
  expect(
    renderer.root.findAll(node => node.props.children === expected).length,
  ).toBeGreaterThan(0);
});

test('conflict refresh preserves dirty description while untouched descriptions follow server state', () => {
  const props = {writesAvailable: true, onTaskEdit: jest.fn()};
  const renderer = render(props);
  act(() => control(renderer, 'Open task: Prepare demo').props.onPress());
  act(() =>
    renderer.update(
      <TasksPage
        loading={false}
        {...props}
        outcome={{
          ...outcome,
          value: {...outcome.value, items: [{...task, title: 'Server title'}]},
        }}
      />,
    ),
  );
  expect(control(renderer, 'Task description').props.value).toBe(
    'Server title',
  );
  act(() =>
    control(renderer, 'Task description').props.onChangeText(
      'My unsaved description',
    ),
  );
  act(() =>
    renderer.update(
      <TasksPage
        loading={false}
        {...props}
        busyTaskId="task-1"
        taskMutationError="Task changed. Copy your edit before dismissing."
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [{...task, title: 'Another server title'}],
          },
        }}
      />,
    ),
  );
  expect(control(renderer, 'Task description').props.value).toBe(
    'My unsaved description',
  );
});

const incompletePage = {
  windowStatus: 'incomplete' as const,
  complete: false,
  hasMore: false,
  nextCursor: null,
  completenessStatus: 'incomplete' as const,
  reasons: ['accepted_work_pending'],
};

test('task grant denial shows the typed error instead of an empty library', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'error',
          error: 'This saved data is not available for this account.',
        }}
        loading={false}
      />,
    );
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('This saved data is not available for this account.');
  expect(copy).not.toContain('No tasks yet.');
  expect(copy).not.toContain('Saved tasks could not be loaded.');
});

test('incomplete empty tasks do not claim a complete library', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: incompletePage,
          },
        }}
        loading={false}
      />,
    );
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Tasks are incomplete.');
  expect(copy).not.toContain('No tasks yet.');
});

test('an incomplete empty task search does not claim a complete miss', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'success',
          value: {
            items: [],
            page: incompletePage,
          },
        }}
        loading={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded tasks')
      .props.onChangeText('nomatch');
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Tasks are incomplete.');
  expect(copy).not.toContain('No loaded tasks match.');
});

test('task pagination stays available when loaded task search has no matches', () => {
  const onLoadMore = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{...outcome, value: {...outcome.value, items: []}}}
        loading={false}
        taskPagination={
          <TaskPagination
            hasMore
            busy={false}
            notice={null}
            onLoadMore={onLoadMore}
          />
        }
      />,
    );
  });
  act(() => control(renderer, 'Load more tasks')!.props.onPress());
  expect(onLoadMore).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});
