import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import type {TaskRead, TaskReadOutcome} from '../src/desktopReadClient';

jest.mock('../src/omiNative', () => ({
  omiBackend: {createWriteId: jest.fn()},
  subscribeOmiBackendSessionInvalidated: () => () => undefined,
}));
jest.mock('../src/taskMutationClient', () => ({
  prepareTaskPatch: jest.fn(),
  sendTaskPatch: jest.fn(),
}));

import {prepareTaskPatch, sendTaskPatch} from '../src/taskMutationClient';
import {useTaskMutations} from '../src/app/useTaskMutations';

const prepare = prepareTaskPatch as jest.Mock;
const send = sendTaskPatch as jest.Mock;
const prepared = {recordId: 'task', writeId: 'a'.repeat(64), body: 'immutable'};
const read: TaskRead = {
  accountEpoch: 0,
  items: [
    {
      kind: 'task',
      id: 'task',
      title: 'Call Sam',
      summary: '',
      searchableText: 'Call Sam',
      completed: false,
      completedAt: null,
      dueAt: null,
      owner: null,
      source: 'user',
      provenance: [],
      sortOrder: 0,
      indentLevel: 0,
      createdAt: 0,
      updatedAt: 0,
      revision: 'b'.repeat(64),
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
};

function Harness(
  props: Parameters<typeof useTaskMutations>[0] & {
    onState: (value: ReturnType<typeof useTaskMutations>) => void;
  },
) {
  props.onState(useTaskMutations(props));
  return null;
}

async function mount(
  outcome: TaskReadOutcome = {status: 'success', value: read},
) {
  let state!: ReturnType<typeof useTaskMutations>;
  const refreshTasks = jest.fn(async (): Promise<TaskRead | null> => read);
  const props = {
    enabled: true,
    outcome,
    refreshTasks,
    revalidateSession: jest.fn(async () => undefined),
    onState: (value: typeof state) => {
      state = value;
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<Harness {...props} />);
  });
  return {
    get state() {
      return state;
    },
    refreshTasks,
    renderer,
    props,
  };
}

beforeEach(() => {
  prepare.mockReset().mockResolvedValue(prepared);
  send.mockReset().mockResolvedValue({ok: true, revision: 'c'.repeat(64)});
});

test('uses epoch zero and refreshes only after acknowledgement without optimistic mutation', async () => {
  const app = await mount();
  await ReactTestRenderer.act(async () => {
    app.state.onTaskToggle('task');
  });
  expect(prepare.mock.calls[0][1]).toEqual({
    recordId: 'task',
    baseRevision: 'b'.repeat(64),
    accountEpoch: 0,
    patch: {completed: true},
  });
  expect(app.refreshTasks).toHaveBeenCalledTimes(1);
  expect(read.items[0].completed).toBe(false);
  expect(app.state.busyTaskId).toBeNull();
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});

test('retains exact prepared operation after ambiguous failure and blocks replacement', async () => {
  send.mockResolvedValueOnce({
    ok: false,
    failure: {kind: 'retryable', detail: 'lost'},
    controlUnavailable: false,
  });
  const app = await mount();
  await ReactTestRenderer.act(async () => {
    app.state.onTaskEdit('task', 'Call Jo');
  });
  expect(app.state.busyTaskId).toBe('task');
  expect(app.refreshTasks).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => {
    app.state.onTaskToggle('task');
  });
  expect(prepare).toHaveBeenCalledTimes(1);
  await ReactTestRenderer.act(async () => app.state.onRetryTaskMutation?.());
  expect(send.mock.calls[0][1]).toBe(send.mock.calls[1][1]);
  expect(app.state.taskMutationError).toBeNull();
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});

test('an acknowledged write retries only its failed read', async () => {
  const app = await mount();
  app.refreshTasks.mockResolvedValueOnce(null);
  await ReactTestRenderer.act(async () => {
    app.state.onTaskToggle('task');
  });
  expect(app.state.taskMutationError).toContain('Saved');
  await ReactTestRenderer.act(async () => app.state.onRetryTaskMutation?.());
  expect(send).toHaveBeenCalledTimes(1);
  expect(app.refreshTasks).toHaveBeenCalledTimes(2);
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});

test('legacy reads without an epoch stay read-only', async () => {
  const app = await mount({
    status: 'success',
    value: {...read, accountEpoch: null},
  });
  expect(app.state.writesAvailable).toBe(false);
  await ReactTestRenderer.act(async () => {
    app.state.onTaskToggle('task');
  });
  expect(prepare).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});

test('sign-out during identity minting retires the write before transport', async () => {
  let resolve!: (value: typeof prepared) => void;
  prepare.mockReturnValue(
    new Promise(value => {
      resolve = value;
    }),
  );
  const app = await mount();
  await ReactTestRenderer.act(async () => {
    app.state.onTaskToggle('task');
  });
  await ReactTestRenderer.act(async () => {
    app.renderer.update(<Harness {...app.props} enabled={false} />);
  });
  await ReactTestRenderer.act(async () => {
    resolve(prepared);
  });
  expect(send).not.toHaveBeenCalled();
  expect(app.state.busyTaskId).toBeNull();
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});

test('permanent epoch refusal keeps the edit visible without retry', async () => {
  send.mockResolvedValue({
    ok: false,
    failure: {kind: 'permanent', reason: 'stale_epoch', detail: 'refused'},
    controlUnavailable: false,
  });
  const app = await mount();
  await ReactTestRenderer.act(async () => {
    app.state.onTaskEdit('task', 'Call Jo');
  });
  expect(app.state.onRetryTaskMutation).toBeUndefined();
  expect(app.state.taskMutationError).toContain('not accepted');
  expect(app.refreshTasks).toHaveBeenCalledTimes(1);
  expect(app.state.busyTaskId).toBe('task');
  await ReactTestRenderer.act(async () => app.state.onDismissTaskMutation?.());
  expect(app.state.busyTaskId).toBeNull();
  await ReactTestRenderer.act(async () => {
    app.renderer.update(
      <Harness
        {...app.props}
        outcome={{status: 'success', value: {...read, accountEpoch: 9}}}
      />,
    );
  });
  send.mockResolvedValue({ok: true, revision: 'd'.repeat(64)});
  await ReactTestRenderer.act(async () => {
    app.state.onTaskEdit('task', 'Reviewed change');
  });
  expect(prepare.mock.calls[1][1].accountEpoch).toBe(9);
  await ReactTestRenderer.act(async () => app.renderer.unmount());
});
