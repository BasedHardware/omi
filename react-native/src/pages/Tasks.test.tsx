import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {TasksPage} from './Tasks';
import {TaskPagination} from '../ui/TaskPagination';
import type {TaskMutationProps} from '../ui/TaskEditor';
import {
  desktopBackendServiceCopy,
  desktopBackendUnavailableCopy,
  type TaskProjection,
} from '../desktopReadClient';

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
  const renderer = render({
    writesAvailable: false,
    onTaskToggle: jest.fn(),
    onTaskEdit: jest.fn(),
  });
  expect(control(renderer, 'Task Prepare demo').props.disabled).toBe(true);
  expect(control(renderer, 'Open Prepare demo')).toBeUndefined();
  expect(control(renderer, 'Open task: Prepare demo')).toBeUndefined();
  act(() => control(renderer, 'Task: Prepare demo').props.onPress());
  expect(control(renderer, 'Task description')).toBeUndefined();
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Task editing is unavailable for this connection.');
});

test('a whitespace-only task title stays visible instead of a blank row', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [{...task, title: ' \t\n'}],
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
  expect(copy).toContain('Task title unavailable');
  expect(copy).not.toContain(' \t\n');
  act(() => renderer.unmount());
});

test('task search matches the visible title fallback for empty titles', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [{...task, title: ''}],
          },
        }}
        loading={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded tasks')
      .props.onChangeText('unavailable');
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Task title unavailable');
  expect(copy).not.toContain('No loaded tasks match.');
  act(() => renderer.unmount());
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
  act(() => control(renderer, 'Task description').props.onChangeText('\u0085'));
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
    year: 'numeric',
    timeZone: 'UTC',
  });
  expect(
    renderer.root.findAll(node => node.props.children === expected).length,
  ).toBeGreaterThan(0);
});

test('task due dates include the year so last-year dues do not look like this year', () => {
  const dueAt = Date.UTC(2025, 11, 31);
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
    year: 'numeric',
    timeZone: 'UTC',
  });
  expect(expected).toContain('2025');
  expect(
    renderer.root.findAll(node => node.props.children === expected).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.children ===
        new Date(dueAt).toLocaleDateString(undefined, {
          day: 'numeric',
          month: 'short',
          timeZone: 'UTC',
        }),
    ).length,
  ).toBe(0);
});

test('task due dates use second-scale epochs as calendar days not 1970', () => {
  const dueAt = 1786000000;
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
  const expected = new Date(dueAt * 1000).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
  expect(expected).toContain('2026');
  expect(expected).not.toContain('1970');
  expect(
    renderer.root.findAll(node => node.props.children === expected).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.children ===
        new Date(dueAt).toLocaleDateString(undefined, {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
          timeZone: 'UTC',
        }),
    ).length,
  ).toBe(0);
});

test('a zero task due timestamp says Date unavailable instead of 1970', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        loading={false}
        outcome={{
          ...outcome,
          value: {...outcome.value, items: [{...task, dueAt: 0}]},
        }}
      />,
    );
  });
  const copy = renderer.root
    .findAllByType(Text)
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
  expect(copy).toContain('Date unavailable');
  expect(copy).not.toContain('1970');
  expect(copy).not.toContain('No due date');
});

test('task rows keep GET indent instead of a flat list', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        loading={false}
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [
              {
                ...task,
                id: 'task-parent',
                title: 'Parent task',
                indentLevel: 0,
              },
              {
                ...task,
                id: 'task-child',
                title: 'Nested child',
                indentLevel: 2,
              },
            ],
          },
        }}
      />,
    );
  });
  const nested = renderer.root.findAll(
    node => node.props.accessibilityLabel === 'Nested task',
  );
  expect(nested.length).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(node =>
      [node.props.style]
        .flat(Infinity)
        .some(
          (entry: {paddingLeft?: number} | null) => entry?.paddingLeft === 70,
        ),
    ).length,
  ).toBeGreaterThan(0);
  act(() => renderer.unmount());
});

test('task rows name GET exported platforms and omit missing exports', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        loading={false}
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [
              {
                ...task,
                id: 'task-exported',
                title: 'Call Sam',
                exportCopy: 'Exported to Todoist',
              },
              {...task, id: 'task-plain', title: 'Write recap'},
            ],
          },
        }}
      />,
    );
  });
  const copy = renderer.root
    .findAllByType(Text)
    .flatMap(node => node.props.children)
    .join(' ');
  expect(copy).toContain('Exported to Todoist');
  expect(copy).toContain('Call Sam');
  expect(copy).toContain('Write recap');
  act(() => renderer.unmount());
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
  expect(copy).not.toContain(
    'Task editing is unavailable for this connection.',
  );
});

test('loading tasks do not claim editing is unavailable', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(<TasksPage outcome={null} loading />);
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Loading tasks…');
  expect(copy).not.toContain(
    'Task editing is unavailable for this connection.',
  );
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

test('a NEXT LINE-only task search keeps rows instead of claiming a miss', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          ...outcome,
          value: {
            ...outcome.value,
            items: [{...task, title: 'Prepare product demo'}],
          },
        }}
        loading={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded tasks')
      .props.onChangeText('\u0085');
  });
  const copy = renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
  expect(copy).toContain('Prepare product demo');
  expect(copy).not.toContain('No loaded tasks match.');
  expect(copy).not.toContain('\u0085');
  act(() => renderer.unmount());
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

const pagedOutcome = {
  status: 'success' as const,
  value: {
    items: [task],
    page: {
      windowStatus: 'more' as const,
      complete: false,
      hasMore: true,
      nextCursor: 'tasks-next',
      completenessStatus: 'complete' as const,
      reasons: [],
    },
  },
};

function taskPageText(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
}

test('nested non-retryable later task pages do not claim more are available', () => {
  const onLoadMore = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={pagedOutcome}
        loading={false}
        taskNotice={desktopBackendUnavailableCopy}
        taskPagination={
          <TaskPagination
            hasMore={false}
            busy={false}
            notice={desktopBackendUnavailableCopy}
            onLoadMore={onLoadMore}
          />
        }
      />,
    );
  });
  const copy = taskPageText(renderer);
  expect(copy).toContain('Prepare demo');
  expect(copy).toContain(desktopBackendUnavailableCopy);
  expect(copy).not.toContain('More tasks are available.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more tasks',
    ),
  ).toHaveLength(0);
  act(() => renderer.unmount());
});

test('retryable later task pages still claim more are available', () => {
  const onLoadMore = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={pagedOutcome}
        loading={false}
        taskNotice="More tasks could not be loaded. Try again."
        taskPagination={
          <TaskPagination
            hasMore
            busy={false}
            notice="More tasks could not be loaded. Try again."
            onLoadMore={onLoadMore}
          />
        }
      />,
    );
  });
  const copy = taskPageText(renderer);
  expect(copy).toContain('More tasks are available.');
  expect(copy).toContain('More tasks could not be loaded. Try again.');
  act(() => control(renderer, 'Load more tasks')!.props.onPress());
  expect(onLoadMore).toHaveBeenCalledTimes(1);
  act(() => renderer.unmount());
});

test('nested non-retryable later task pages do not claim more are available in an empty search', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={pagedOutcome}
        loading={false}
        taskNotice={desktopBackendUnavailableCopy}
        taskPagination={
          <TaskPagination
            hasMore={false}
            busy={false}
            notice={desktopBackendUnavailableCopy}
            onLoadMore={jest.fn()}
          />
        }
      />,
    );
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Search loaded tasks')
      .props.onChangeText('nomatch');
  });
  const copy = taskPageText(renderer);
  expect(copy).toContain('No loaded tasks match.');
  expect(copy).toContain(desktopBackendUnavailableCopy);
  expect(copy).not.toContain('More tasks are available.');
  act(() => renderer.unmount());
});

test('nested non-retryable task reads omit Refresh', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'error',
          error: desktopBackendUnavailableCopy,
        }}
        loading={false}
        onRefresh={jest.fn()}
      />,
    );
  });
  expect(taskPageText(renderer)).toContain(desktopBackendUnavailableCopy);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh tasks',
    ),
  ).toHaveLength(0);
  act(() => renderer.unmount());
});

test('retryable task reads still offer Refresh', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'error',
          error:
            'This saved data could not be loaded. Retry without changing it.',
        }}
        loading={false}
        onRefresh={jest.fn()}
      />,
    );
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Refresh tasks',
    ).length,
  ).toBeGreaterThan(0);
  act(() => renderer.unmount());
});

test('tasks page names past-due GET due_at as Overdue matching Flutter tasksOverdue', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'success',
          value: {
            items: [{...task, id: 'task-overdue', dueAt: Date.UTC(2020, 0, 1)}],
            page: outcome.value.page,
          },
        }}
        loading={false}
      />,
    );
  });
  const copy = taskPageText(renderer);
  expect(copy).toContain('Overdue');
  expect(copy).toContain('Prepare demo');
  expect(copy).not.toContain('Today');
  act(() => renderer.unmount());
});

test('tasks page names undated GET due_at as No Deadline matching Flutter tasksNoDeadline', () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        outcome={{
          status: 'success',
          value: {
            items: [
              {
                ...task,
                id: 'task-undated',
                dueAt: null,
                createdAt: Date.now(),
              },
            ],
            page: outcome.value.page,
          },
        }}
        loading={false}
      />,
    );
  });
  const copy = taskPageText(renderer);
  expect(copy).toContain('No Deadline');
  expect(copy).toContain('Prepare demo');
  expect(copy).not.toContain('Later');
  expect(copy).not.toContain('Overdue');
  act(() => renderer.unmount());
});

test('tasks page names GET goals without add or a write sheet', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'goal-read',
            title: 'Read 20 books',
            current_value: 3,
            target_value: 10,
          },
          {id: 'goal-empty', title: ' \t', current_value: 1, target_value: 2},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        backend={{request} as never}
        outcome={outcome}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = taskPageText(renderer);
  expect(tree).toContain('Goals');
  expect(tree).toContain('Read 20 books');
  expect(tree).toContain('3/10');
  expect(tree).toContain('Prepare demo');
  expect(tree).not.toContain('goal-read');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('🎯');
  expect(tree).not.toContain('Add');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/goals/all',
  });
  expect(request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
  expect(request.mock.calls.some(call => call[0].path === '/v1/goals')).toBe(
    false,
  );
  act(() => renderer.unmount());
});

test('tasks page names a failed GET goals instead of empty success', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        backend={{request} as never}
        outcome={outcome}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = taskPageText(renderer);
  expect(tree).toContain('Goals');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).toContain('Prepare demo');
  expect(tree).not.toContain('No goals');
  expect(tree).not.toContain('🎯');
  expect(tree).not.toContain('Add');
  expect(request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
  expect(request.mock.calls.some(call => call[0].path === '/v1/goals')).toBe(
    false,
  );
  act(() => renderer.unmount());
});

test('tasks page omits GET goals on failure rather than inventing No goals', async () => {
  const request = jest.fn(async request => {
    if (request.path === '/v1/goals/all') {
      return {id: request.id, status: 404, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <TasksPage
        backend={{request} as never}
        outcome={{
          status: 'success',
          value: {items: [], page: outcome.value.page},
        }}
        loading={false}
      />,
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = taskPageText(renderer);
  expect(tree).toContain('No tasks yet.');
  expect(tree).not.toContain('Goals');
  expect(tree).not.toContain('No goals');
  act(() => renderer.unmount());
});
