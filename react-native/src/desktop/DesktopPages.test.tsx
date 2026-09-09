import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {TasksPage} from './DesktopPages';
import type {DesktopReadOutcomes} from '../desktopReadClient';

function outcomes(legacy: boolean): DesktopReadOutcomes {
  return {
    conversations: {status: 'error', error: 'unused'},
    memories: {status: 'error', error: 'unused'},
    tasks: {
      status: 'success',
      value: {
        ...(legacy ? {apiContract: 'omi' as const} : {}),
        accountEpoch: null,
        items: [
          {
            kind: 'task',
            id: 'task-1',
            title: 'Review notes',
            summary: '',
            searchableText: 'review notes',
            completed: false,
            completedAt: null,
            dueAt: null,
            owner: null,
            source: 'omi',
            provenance: [],
            sortOrder: 0,
            indentLevel: 0,
            createdAt: null,
            updatedAt: null,
            revision: null,
          },
        ],
        page: {
          windowStatus: 'complete',
          complete: true,
          hasMore: false,
          nextCursor: null,
          completenessStatus: 'complete',
          reasons: [],
        },
      },
    },
  };
}
const mounted: ReactTestRenderer.ReactTestRenderer[] = [];
function render(
  legacy: boolean,
  extra: Partial<React.ComponentProps<typeof TasksPage>> = {},
) {
  const props = {
    outcomes: outcomes(legacy),
    writesAvailable: true,
    onTaskToggle: jest.fn(),
    onTaskEdit: jest.fn(),
    ...extra,
  };
  let view!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    view = ReactTestRenderer.create(<TasksPage {...props} />);
  });
  mounted.push(view);
  return {view, props};
}
function label(view: ReactTestRenderer.ReactTestRenderer, name: string) {
  return view.root.findAll(node => node.props.accessibilityLabel === name)[0]!;
}
afterEach(() => act(() => mounted.splice(0).forEach(view => view.unmount())));

test('legacy tasks without revisions toggle and save edited descriptions', () => {
  const {view, props} = render(true);
  const toggle = label(view, 'Complete task: Review notes');
  expect(toggle.props.disabled).toBe(false);
  expect(toggle.props.accessibilityState.disabled).toBe(false);
  act(() => toggle.props.onPress());
  expect(props.onTaskToggle).toHaveBeenCalledWith('task-1');
  act(() => label(view, 'Edit task: Review notes').props.onPress());
  act(() =>
    label(view, 'Task description').props.onChangeText('Review all notes'),
  );
  expect(label(view, 'Save task description').props.disabled).toBe(false);
  act(() => label(view, 'Save task description').props.onPress());
  expect(props.onTaskEdit).toHaveBeenCalledWith('task-1', 'Review all notes');
});

test('canonical tasks without revisions remain disabled and hide edit', () => {
  const {view} = render(false);
  expect(label(view, 'Complete task: Review notes').props.disabled).toBe(true);
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Edit task: Review notes',
    ),
  ).toHaveLength(0);
});

test('pending mutations disable both legacy actions and saving an open editor', () => {
  const {view, props} = render(true);
  act(() => label(view, 'Edit task: Review notes').props.onPress());
  act(() => label(view, 'Task description').props.onChangeText('Changed'));
  act(() => view.update(<TasksPage {...props} busyTaskId="another-task" />));
  expect(label(view, 'Complete task: Review notes').props.disabled).toBe(true);
  expect(label(view, 'Edit task: Review notes').props.disabled).toBe(true);
  expect(label(view, 'Save task description').props.disabled).toBe(true);
  expect(label(view, 'Task description').props.editable).toBe(false);
});

test('lost write eligibility closes an open editor and disables completion', () => {
  const {view, props} = render(true);
  act(() => label(view, 'Edit task: Review notes').props.onPress());
  act(() => view.update(<TasksPage {...props} outcomes={outcomes(false)} />));
  expect(label(view, 'Complete task: Review notes').props.disabled).toBe(true);
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Task description',
    ),
  ).toHaveLength(0);
  act(() => view.update(<TasksPage {...props} writesAvailable={false} />));
  expect(label(view, 'Complete task: Review notes').props.disabled).toBe(true);
  expect(
    view.root.findAll(
      node => node.props.accessibilityLabel === 'Edit task: Review notes',
    ),
  ).toHaveLength(0);
});
