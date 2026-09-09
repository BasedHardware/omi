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

function libraryOutcome(): DesktopReadOutcomes {
  const base = outcomes(false);
  return {
    ...base,
    conversations: {
      status: 'success',
      value: {
        page:
          base.tasks.status === 'success'
            ? {...base.tasks.value.page, hasMore: true}
            : null!,
        items: [
          {
            kind: 'conversation',
            id: 'conversation-1',
            title: 'Planning',
            summary: 'Launch plan',
            searchableText: 'planning launch plan',
            createdAt: '2026-09-09T00:00:00Z',
            updatedAt: null,
            startedAt: null,
            finishedAt: null,
            starred: false,
            status: 'completed',
            source: 'import',
            visibility: 'private',
            folderId: null,
            locked: false,
            discarded: false,
          },
        ],
      },
    },
  };
}

test('library rows open shared details, go back, and paginate without a second search', () => {
  const {LibraryPage} = require('./DesktopPages');
  const {TextInput} = require('react-native');
  const onLoadMore = jest.fn();
  const props = {outcomes: libraryOutcome(), onLoadMore};
  let view!: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    view = ReactTestRenderer.create(<LibraryPage {...props} />);
  });
  mounted.push(view);
  expect(view.root.findAllByType(TextInput)).toHaveLength(0);
  act(() => label(view, 'Load more conversations').props.onPress());
  expect(onLoadMore).toHaveBeenCalledTimes(1);
  act(() => label(view, 'Open conversation Planning').props.onPress());
  expect(label(view, 'Selected conversation details')).toBeDefined();
  act(() => label(view, 'Back to conversations').props.onPress());
  expect(label(view, 'Open conversation Planning')).toBeDefined();
  act(() => view.update(<LibraryPage {...props} loadingMore />));
  expect(label(view, 'Load more conversations').props.disabled).toBe(true);
});

test.each(['missing', 'error', 'query'])(
  'library retires selected detail after %s and does not restore it',
  mode => {
    const {LibraryPage} = require('./DesktopPages');
    const initial = libraryOutcome();
    let view!: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      view = ReactTestRenderer.create(<LibraryPage outcomes={initial} />);
    });
    mounted.push(view);
    act(() => label(view, 'Open conversation Planning').props.onPress());
    const changed = {
      ...initial,
      conversations:
        mode === 'error'
          ? {status: 'error', error: 'Sign in again'}
          : {
              status: 'success',
              value: {
                ...((initial.conversations as {value: unknown})
                  .value as object),
                items: [],
              },
            },
    };
    act(() =>
      view.update(
        <LibraryPage
          outcomes={mode === 'query' ? initial : changed}
          query={mode === 'query' ? 'unmatched' : ''}
        />,
      ),
    );
    expect(
      view.root.findAll(
        node =>
          node.props.accessibilityLabel === 'Selected conversation details',
      ),
    ).toHaveLength(0);
    act(() => view.update(<LibraryPage outcomes={initial} />));
    expect(label(view, 'Open conversation Planning')).toBeDefined();
  },
);

test.each(['completed', 'processing'])(
  'untitled %s conversation has a useful label and a leading back button',
  status => {
    const {LibraryPage} = require('./DesktopPages');
    const {StyleSheet} = require('react-native');
    const value = libraryOutcome();
    if (value.conversations.status !== 'success')
      throw new Error('Expected fixture');
    value.conversations.value.items[0]!.title = '';
    value.conversations.value.items[0]!.status = status;
    let view!: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      view = ReactTestRenderer.create(<LibraryPage outcomes={value} />);
    });
    mounted.push(view);
    const title =
      status === 'processing'
        ? 'Processing conversation…'
        : 'Conversation title unavailable';
    act(() => label(view, `Open conversation ${title}`).props.onPress());
    expect(
      StyleSheet.flatten(label(view, 'Back to conversations').props.style)
        .alignSelf,
    ).toBe('flex-start');
  },
);
