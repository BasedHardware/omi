import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

jest.mock('../src/desktopReadClient', () => {
  const actual = jest.requireActual('../src/desktopReadClient');
  return {
    ...actual,
    loadDesktopReads: jest.fn(),
    loadTasks: jest.fn(),
    loadConversations: jest.fn(),
    loadMemories: jest.fn(),
  };
});

jest.mock('../src/omiNative', () => ({
  omiBackend: {request: jest.fn()},
  omiNative: undefined,
  omiAuth: undefined,
}));

import {useDesktopReads} from '../src/app/useDesktopReads';
import {
  desktopBackendServiceCopy,
  desktopProjectionUnavailableCopy,
  desktopBackendUnavailableCopy,
  loadDesktopReads,
  loadTasks,
  loadConversations,
  loadMemories,
  ConversationCursorExpiredError,
  TaskCursorExpiredError,
} from '../src/desktopReadClient';

const readsMock = loadDesktopReads as jest.Mock;
import type {DesktopReadOutcomes} from '../src/desktopReadClient';

function conversationItem(id: string, title: string) {
  return {
    kind: 'conversation' as const,
    id,
    title,
    summary: title,
    searchableText: title,
    createdAt: '2026-09-01T10:00:00.000Z',
    updatedAt: '2026-09-01T10:00:00.000Z',
    startedAt: '2026-09-01T10:00:00.000Z',
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'desktop',
    visibility: 'private' as const,
    folderId: null,
    locked: false,
    discarded: false,
  };
}

function successOutcomes(titles: string[]): DesktopReadOutcomes {
  const items = titles.map(title => conversationItem(title, title));
  return {
    conversations: {
      status: 'success',
      value: {
        items,
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
    memories: {
      status: 'success',
      value: {
        items: [],
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
    tasks: {
      status: 'success',
      value: {
        accountEpoch: null,
        items: [],
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

const errorOutcomes: DesktopReadOutcomes = {
  conversations: {
    status: 'error',
    error: 'Omi cloud needs a signed-in session.',
  },
  memories: {status: 'error', error: 'Omi cloud needs a signed-in session.'},
  tasks: {status: 'error', error: 'Omi cloud needs a signed-in session.'},
};

function Harness({
  enabled,
  onState,
}: {
  enabled: boolean;
  onState: (state: ReturnType<typeof useDesktopReads>) => void;
}) {
  const state = useDesktopReads({enabled});
  onState(state);
  return null;
}

async function renderReads(props: {enabled: boolean}) {
  const states: ReturnType<typeof useDesktopReads>[] = [];
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(
      <Harness enabled={props.enabled} onState={state => states.push(state)} />,
    );
  });
  return {
    latest: () => states[states.length - 1]!,
    rerender: async (next: {enabled: boolean}) => {
      await ReactTestRenderer.act(async () => {
        renderer!.update(
          <Harness enabled={next.enabled} onState={s => states.push(s)} />,
        );
      });
    },
    unmount: () => {
      ReactTestRenderer.act(() => {
        renderer!.unmount();
      });
    },
  };
}

beforeEach(() => {
  readsMock.mockReset();
  (loadConversations as jest.Mock).mockReset();
  (loadMemories as jest.Mock).mockReset();
  (loadTasks as jest.Mock).mockReset();
});

test('ignoreEnabled loads while the gate is still closed', async () => {
  readsMock.mockResolvedValue(successOutcomes(['After sign-in']));
  const reads = await renderReads({enabled: false});
  expect(reads.latest().reads).toEqual([]);

  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });
  expect(reads.latest().reads).toEqual([]);

  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false, {ignoreEnabled: true});
  });
  expect(reads.latest().reads.map(item => item.id)).toEqual(['After sign-in']);
  expect(reads.latest().readsPhase).toBe('ready');
  reads.unmount();
});

test('ignoreEnabled post-sign-in load is not retired by the enablement effect', async () => {
  // signInAndRefresh awaits ignoreEnabled while enabled is still false; the
  // gate then flips true. The enablement effect must not start a second
  // refresh that retires the awaited one, or await would resolve without the
  // rows it claimed to load.
  let resolveSignIn!: (value: DesktopReadOutcomes) => void;
  readsMock.mockImplementationOnce(
    () =>
      new Promise<DesktopReadOutcomes>(resolve => {
        resolveSignIn = resolve;
      }),
  );
  readsMock.mockResolvedValueOnce(successOutcomes(['EFFECT SHOULD NOT WIN']));

  const reads = await renderReads({enabled: false});
  let signInLoad!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    signInLoad = reads.latest().refreshReads(false, {ignoreEnabled: true});
  });
  expect(readsMock).toHaveBeenCalledTimes(1);

  await reads.rerender({enabled: true});
  // Enablement must not fire a second cloud load.
  expect(readsMock).toHaveBeenCalledTimes(1);

  await ReactTestRenderer.act(async () => {
    resolveSignIn(successOutcomes(['Sign-in rows']));
    await signInLoad;
  });
  expect(reads.latest().reads.map(item => item.id)).toEqual(['Sign-in rows']);
  expect(reads.latest().readsPhase).toBe('ready');
  expect(readsMock).toHaveBeenCalledTimes(1);
  reads.unmount();
});

test('orders Home timeline by normalized conversation and memory time', async () => {
  // Port of superseded #12141 — memories are epoch seconds; conversations are ms.
  const olderConversation = conversationItem('older-conversation', 'Older');
  olderConversation.startedAt = '2026-09-01T10:00:00.000Z';
  olderConversation.createdAt = '2026-09-01T10:00:00.000Z';
  const newerConversation = conversationItem('newer-conversation', 'Newer');
  newerConversation.startedAt = '2026-09-03T10:00:00.000Z';
  newerConversation.createdAt = '2026-09-03T10:00:00.000Z';
  const memorySeconds = Math.floor(
    new Date('2026-09-02T12:00:00.000Z').getTime() / 1000,
  );
  const memory = {
    kind: 'memory' as const,
    id: 'mid-memory',
    title: 'Memory',
    summary: 'Memory',
    searchableText: 'Memory',
    citations: [] as never[],
    timestamp: memorySeconds,
    provenance: {
      label: null,
      synthesisVersion: 'v1',
      inputDigest: 'a',
      outputDigest: 'b',
    },
  };
  const page = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [] as string[],
  };
  readsMock.mockResolvedValue({
    conversations: {
      status: 'success',
      value: {items: [olderConversation, newerConversation], page},
    },
    memories: {status: 'success', value: {items: [memory], page}},
    tasks: {status: 'success', value: {items: [], page}},
  });

  const reads = await renderReads({enabled: true});
  expect(reads.latest().reads.map(item => item.id)).toEqual([
    'newer-conversation',
    'mid-memory',
    'older-conversation',
  ]);
  reads.unmount();
});

test('missing timestamps sort after dated Home rows', async () => {
  const dated = conversationItem('dated', 'Dated');
  dated.startedAt = '2026-09-02T10:00:00.000Z';
  dated.createdAt = '2026-09-02T10:00:00.000Z';
  const undatedMemory = {
    kind: 'memory' as const,
    id: 'undated-memory',
    title: 'Undated',
    summary: 'Undated',
    searchableText: 'Undated',
    citations: [] as never[],
    timestamp: null,
    provenance: {
      label: null,
      synthesisVersion: 'v1',
      inputDigest: 'a',
      outputDigest: 'b',
    },
  };
  const page = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [] as string[],
  };
  readsMock.mockResolvedValue({
    conversations: {status: 'success', value: {items: [dated], page}},
    memories: {status: 'success', value: {items: [undatedMemory], page}},
    tasks: {status: 'success', value: {items: [], page}},
  });
  const reads = await renderReads({enabled: true});
  expect(reads.latest().reads.map(item => item.id)).toEqual([
    'dated',
    'undated-memory',
  ]);
  reads.unmount();
});

test('a successful refresh inside the live session lands as saved rows', async () => {
  readsMock.mockResolvedValue(successOutcomes(['Account A conversation']));
  const reads = await renderReads({enabled: true});
  expect(reads.latest().reads.map(item => item.id)).toEqual([
    'Account A conversation',
  ]);
  expect(reads.latest().readsPhase).toBe('ready');
  reads.unmount();
});

test('a task failure makes the read phase unavailable even when other domains succeed', async () => {
  const outcomes = successOutcomes([]);
  outcomes.tasks = {
    status: 'error',
    error: 'Tasks could not be loaded.',
  };
  readsMock.mockResolvedValue(outcomes);

  const reads = await renderReads({enabled: true});
  expect(reads.latest().readsPhase).toBe('unavailable');
  reads.unmount();
});

test('a late refresh from a dropped session cannot seed the next session', async () => {
  // The session drops (enabled false) while its refresh is still in flight.
  // When that refresh resolves afterwards, its rows must be discarded —
  // otherwise the next session's failed load reports "saved data" built from
  // the previous account's rows.
  let resolveFirst!: (value: DesktopReadOutcomes) => void;
  readsMock.mockImplementationOnce(
    () =>
      new Promise<DesktopReadOutcomes>(resolve => {
        resolveFirst = resolve;
      }),
  );
  readsMock.mockRejectedValueOnce(new Error('transport failed'));

  const reads = await renderReads({enabled: true});
  expect(reads.latest().readsPhase).toBe('initial-loading');

  await reads.rerender({enabled: false});
  expect(reads.latest().reads).toEqual([]);
  expect(reads.latest().readOutcomes).toBeNull();

  // The dropped session's refresh settles after the gate already left.
  await ReactTestRenderer.act(async () => {
    resolveFirst(successOutcomes(['ACCOUNT A PRIVATE ROW']));
  });
  expect(reads.latest().reads).toEqual([]);
  expect(reads.latest().readOutcomes).toBeNull();

  // The next session signs in and its first load fails: nothing may claim
  // saved rows from the account that just left.
  await reads.rerender({enabled: true});
  await ReactTestRenderer.act(async () => {
    await Promise.resolve();
  });
  expect(reads.latest().reads).toEqual([]);
  expect(reads.latest().readsPhase).toBe('unavailable');
  reads.unmount();
});

test('a retry inside the live session keeps showing saved rows on failure', async () => {
  readsMock.mockResolvedValueOnce(successOutcomes(['Kept conversation']));
  const reads = await renderReads({enabled: true});
  expect(reads.latest().readsPhase).toBe('ready');

  readsMock.mockResolvedValueOnce({
    conversations: {status: 'error', error: desktopBackendServiceCopy},
    memories: {status: 'error', error: desktopBackendServiceCopy},
    tasks: {status: 'error', error: desktopBackendServiceCopy},
  });
  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });
  // A failed refresh inside the SAME session is a truthful degraded phase
  // with the rows it already saved — the fence only retires cross-session
  // and superseded refreshes.
  expect(reads.latest().readsPhase).toBe('saved-but-refresh-failed');
  expect(reads.latest().reads.map(item => item.id)).toEqual([
    'Kept conversation',
  ]);
  reads.unmount();
});

test('a retry exposes a dead session after successful reads', async () => {
  readsMock.mockResolvedValueOnce(successOutcomes(['Expired conversation']));
  const reads = await renderReads({enabled: true});

  readsMock.mockResolvedValueOnce(errorOutcomes);
  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });

  expect(reads.latest().readOutcomes).toEqual(errorOutcomes);
  expect(reads.latest().reads).toEqual([]);
  // Non-transient auth failures replace prior rows — the shell must not claim
  // it is still "showing saved data" once those rows are gone.
  expect(reads.latest().readsPhase).toBe('unavailable');
  reads.unmount();
});

test('a retry replaces a stale error with the current failure', async () => {
  readsMock.mockResolvedValueOnce(errorOutcomes);
  const reads = await renderReads({enabled: true});

  const currentOutcomes: DesktopReadOutcomes = {
    ...errorOutcomes,
    memories: {status: 'error', error: desktopProjectionUnavailableCopy},
  };
  readsMock.mockResolvedValueOnce(currentOutcomes);
  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });

  expect(reads.latest().readOutcomes?.memories).toEqual(
    currentOutcomes.memories,
  );
  reads.unmount();
});

test('reset retires rows before a software-plane refresh', async () => {
  readsMock.mockResolvedValueOnce(successOutcomes(['Old plane row']));
  const reads = await renderReads({enabled: true});
  expect(reads.latest().reads).toHaveLength(1);

  ReactTestRenderer.act(() => {
    reads.latest().resetReads();
  });
  expect(reads.latest().reads).toEqual([]);
  expect(reads.latest().readOutcomes).toBeNull();
  expect(reads.latest().readsPhase).toBe('initial-loading');
  reads.unmount();
});

test('a thrown refresh after empty success is unavailable, not saved', async () => {
  readsMock.mockResolvedValueOnce(successOutcomes([]));
  const reads = await renderReads({enabled: true});
  expect(reads.latest().readsPhase).toBe('ready');
  expect(reads.latest().reads).toEqual([]);

  readsMock.mockRejectedValueOnce(new Error('transport failed'));
  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });
  expect(reads.latest().readsPhase).toBe('unavailable');
  reads.unmount();
});

test('an older superseded refresh cannot overwrite a newer refresh', async () => {
  let resolveOlder!: (value: DesktopReadOutcomes) => void;
  readsMock.mockImplementationOnce(
    () =>
      new Promise<DesktopReadOutcomes>(resolve => {
        resolveOlder = resolve;
      }),
  );
  readsMock.mockResolvedValueOnce(successOutcomes(['Newer result']));

  const reads = await renderReads({enabled: true});
  await ReactTestRenderer.act(async () => {
    await reads.latest().refreshReads(false);
  });
  expect(reads.latest().reads.map(item => item.id)).toEqual(['Newer result']);

  await ReactTestRenderer.act(async () => {
    resolveOlder(successOutcomes(['STALE RESULT']));
  });
  expect(reads.latest().reads.map(item => item.id)).toEqual(['Newer result']);
  reads.unmount();
});

test('task-only refresh preserves the account epoch and retires late session reads', async () => {
  readsMock.mockResolvedValue(successOutcomes(['Saved']));
  const reads = await renderReads({enabled: true});
  const outcome = successOutcomes([]).tasks;
  if (outcome.status !== 'success') {
    throw new Error('fixture');
  }
  const taskRead = {...outcome.value, accountEpoch: 8};
  (loadTasks as jest.Mock).mockResolvedValueOnce(taskRead);
  await ReactTestRenderer.act(async () => {
    expect(await reads.latest().refreshTasks()).toEqual(taskRead);
  });
  expect(reads.latest().readOutcomes?.tasks).toEqual({
    status: 'success',
    value: taskRead,
  });
  let resolve!: (value: typeof taskRead) => void;
  (loadTasks as jest.Mock).mockReturnValueOnce(
    new Promise(value => {
      resolve = value;
    }),
  );
  let pending!: ReturnType<ReturnType<typeof useDesktopReads>['refreshTasks']>;
  await ReactTestRenderer.act(async () => {
    pending = reads.latest().refreshTasks();
  });
  await reads.rerender({enabled: false});
  await ReactTestRenderer.act(async () => {
    resolve(taskRead);
    await pending;
  });
  expect(reads.latest().readOutcomes).toBeNull();
  reads.unmount();
});

function pagedOutcomes() {
  const result = successOutcomes(['Old page']);
  if (result.conversations.status === 'success') {
    result.conversations.value.page = {
      ...result.conversations.value.page,
      hasMore: true,
      complete: false,
      windowStatus: 'more',
      nextCursor: 'cursor-one',
    };
  }
  return result;
}

test('conversation pagination appends one page and ignores duplicate presses', async () => {
  readsMock.mockResolvedValue(pagedOutcomes());
  const reads = await renderReads({enabled: true});
  let release!: (value: unknown) => void;
  (loadConversations as jest.Mock).mockReturnValue(
    new Promise(resolve => (release = resolve)),
  );
  let pending!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    pending = reads.latest().loadMoreConversations();
    void reads.latest().loadMoreConversations();
  });
  expect(loadConversations).toHaveBeenCalledTimes(1);
  expect(reads.latest().conversationsLoadingMore).toBe(true);
  const next = successOutcomes(['Next page']).conversations;
  if (next.status !== 'success') {
    throw Error('fixture');
  }
  await ReactTestRenderer.act(async () => {
    release(next.value);
    await pending;
  });
  expect(reads.latest().readOutcomes?.conversations).toMatchObject({
    value: {items: [{title: 'Old page'}, {title: 'Next page'}]},
  });
  expect(reads.latest().conversationsLoadingMore).toBe(false);
  reads.unmount();
});
test('an expired conversation cursor replaces the old page once and does not loop', async () => {
  readsMock.mockResolvedValue(pagedOutcomes());
  const reads = await renderReads({enabled: true});
  const fresh = successOutcomes(['Fresh first page']).conversations;
  if (fresh.status !== 'success') {
    throw Error('fixture');
  }
  (loadConversations as jest.Mock)
    .mockRejectedValueOnce(new ConversationCursorExpiredError())
    .mockResolvedValueOnce(fresh.value);
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreConversations();
  });
  expect(
    (loadConversations as jest.Mock).mock.calls.map(call => call[1]),
  ).toEqual(['cursor-one', undefined]);
  expect(reads.latest().readOutcomes?.conversations).toMatchObject({
    value: {items: [{title: 'Fresh first page'}]},
  });
  expect(reads.latest().conversationNotice).toContain('refreshed');
  reads.unmount();
});
test.each(['refresh', 'disable'])(
  'a late conversation page cannot overwrite %s',
  async action => {
    readsMock.mockResolvedValue(pagedOutcomes());
    const reads = await renderReads({enabled: true});
    let release!: (value: unknown) => void;
    (loadConversations as jest.Mock).mockReturnValue(
      new Promise(resolve => (release = resolve)),
    );
    let pending!: Promise<void>;
    await ReactTestRenderer.act(async () => {
      pending = reads.latest().loadMoreConversations();
    });
    if (action === 'disable') {
      await reads.rerender({enabled: false});
    } else {
      readsMock.mockResolvedValue(successOutcomes(['New refresh']));
      await ReactTestRenderer.act(async () => {
        await reads.latest().refreshReads(false);
      });
    }
    const stale = successOutcomes(['Late page']).conversations;
    if (stale.status !== 'success') {
      throw Error('fixture');
    }
    await ReactTestRenderer.act(async () => {
      release(stale.value);
      await pending;
    });
    expect(JSON.stringify(reads.latest().readOutcomes)).not.toContain(
      'Late page',
    );
    expect(reads.latest().conversationsLoadingMore).toBe(false);
    reads.unmount();
  },
);
test('failed cursor recovery retains loaded rows and allows explicit retry', async () => {
  readsMock.mockResolvedValue(pagedOutcomes());
  const reads = await renderReads({enabled: true});
  (loadConversations as jest.Mock).mockRejectedValue(
    new ConversationCursorExpiredError(),
  );
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreConversations();
  });
  expect(loadConversations).toHaveBeenCalledTimes(2);
  expect(reads.latest().conversationNotice).toContain('Try again');
  expect(reads.latest().readOutcomes?.conversations).toMatchObject({
    value: {items: [{title: 'Old page'}]},
  });
  reads.unmount();
});

test('nested non-retryable conversation pages omit Load more Try again', async () => {
  readsMock.mockResolvedValue(pagedOutcomes());
  const reads = await renderReads({enabled: true});
  (loadConversations as jest.Mock).mockRejectedValue(
    new Error(desktopBackendUnavailableCopy),
  );
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreConversations();
  });
  expect(reads.latest().conversationNotice).toBe(desktopBackendUnavailableCopy);
  expect(reads.latest().conversationNotice).not.toContain('Try again');
  expect(reads.latest().conversationsPageRetryable).toBe(false);
  expect(reads.latest().readOutcomes?.conversations).toMatchObject({
    value: {items: [{title: 'Old page'}]},
  });
  reads.unmount();
});

function pagedMemoryOutcomes() {
  const result = successOutcomes(['Kept conversation']);
  if (result.memories.status !== 'success') {
    throw Error('fixture');
  }
  result.memories.value.items = [
    {
      kind: 'memory',
      id: 'memory-old',
      title: 'Old memory',
      summary: 'Old memory',
      searchableText: 'Old memory',
      citations: [],
      timestamp: 1,
      provenance: {
        label: null,
        synthesisVersion: 'v1',
        inputDigest: 'a',
        outputDigest: 'b',
      },
    },
  ];
  result.memories.value.page = {
    ...result.memories.value.page,
    hasMore: true,
    complete: false,
    windowStatus: 'more',
    nextCursor: 'memory-cursor-one',
  };
  return result;
}

test('memory pagination appends one page and ignores duplicate presses', async () => {
  readsMock.mockResolvedValue(pagedMemoryOutcomes());
  const reads = await renderReads({enabled: true});
  let release!: (value: unknown) => void;
  (loadMemories as jest.Mock).mockReturnValue(
    new Promise(resolve => (release = resolve)),
  );
  let pending!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    pending = reads.latest().loadMoreMemories();
    void reads.latest().loadMoreMemories();
  });
  expect(loadMemories).toHaveBeenCalledTimes(1);
  expect(reads.latest().memoriesLoadingMore).toBe(true);
  await ReactTestRenderer.act(async () => {
    release({
      items: [
        {
          kind: 'memory',
          id: 'memory-next',
          title: 'Next memory',
          summary: 'Next memory',
          searchableText: 'Next memory',
          citations: [],
          timestamp: 2,
          provenance: {
            label: null,
            synthesisVersion: 'v1',
            inputDigest: 'a',
            outputDigest: 'b',
          },
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
    });
    await pending;
  });
  expect(reads.latest().readOutcomes?.memories).toMatchObject({
    value: {items: [{title: 'Old memory'}, {title: 'Next memory'}]},
  });
  expect(reads.latest().memoriesLoadingMore).toBe(false);
  reads.unmount();
});

test('nested non-retryable memory pages omit Load more Try again', async () => {
  readsMock.mockResolvedValue(pagedMemoryOutcomes());
  const reads = await renderReads({enabled: true});
  (loadMemories as jest.Mock).mockRejectedValue(
    new Error(desktopBackendUnavailableCopy),
  );
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreMemories();
  });
  expect(reads.latest().memoryNotice).toBe(desktopBackendUnavailableCopy);
  expect(reads.latest().memoryNotice).not.toContain('Try again');
  expect(reads.latest().memoriesPageRetryable).toBe(false);
  expect(reads.latest().readOutcomes?.memories).toMatchObject({
    value: {items: [{title: 'Old memory'}]},
  });
  reads.unmount();
});

test('generic later-page memory failures keep loaded rows and allow retry', async () => {
  readsMock.mockResolvedValue(pagedMemoryOutcomes());
  const reads = await renderReads({enabled: true});
  (loadMemories as jest.Mock).mockRejectedValue(new Error('blip'));
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreMemories();
  });
  expect(reads.latest().memoryNotice).toBe(
    'More memories could not be loaded.',
  );
  expect(reads.latest().memoriesPageRetryable).toBe(true);
  expect(reads.latest().readOutcomes?.memories).toMatchObject({
    value: {items: [{title: 'Old memory'}]},
  });
  reads.unmount();
});

function taskOutcomes(
  start = 0,
  count = 25,
  hasMore = true,
  accountEpoch = 7,
): DesktopReadOutcomes {
  const result = successOutcomes([]);
  if (result.tasks.status !== 'success') throw Error('fixture');
  result.tasks.value.accountEpoch = accountEpoch;
  result.tasks.value.page = {
    ...result.tasks.value.page,
    hasMore,
    nextCursor: hasMore ? 'tasks-next' : null,
    complete: !hasMore,
    windowStatus: hasMore ? 'more' : 'complete',
  };
  result.tasks.value.items = Array.from({length: count}, (_, index) => ({
    kind: 'task',
    id: `task-${start + index}`,
    title: `Task ${start + index}`,
    summary: 'Pending',
    searchableText: '',
    completed: false,
    completedAt: null,
    dueAt: null,
    owner: null,
    source: 'assistant',
    provenance: [],
    sortOrder: index,
    indentLevel: 0,
    createdAt: 1,
    updatedAt: 1,
    revision: 'revision',
  }));
  return result;
}
function taskValue(outcomes: DesktopReadOutcomes) {
  if (outcomes.tasks.status !== 'success') throw Error('fixture');
  return outcomes.tasks.value;
}

test('task pagination exposes the 26th task and prevents duplicate in-flight pages', async () => {
  readsMock.mockResolvedValue(taskOutcomes());
  const reads = await renderReads({enabled: true});
  let release!: (value: unknown) => void;
  (loadTasks as jest.Mock).mockReturnValueOnce(
    new Promise(resolve => {
      release = resolve;
    }),
  );
  let pending!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    pending = reads.latest().loadMoreTasks();
    void reads.latest().loadMoreTasks();
  });
  expect(loadTasks).toHaveBeenCalledTimes(1);
  expect(loadTasks).toHaveBeenCalledWith(expect.anything(), 'tasks-next');
  await ReactTestRenderer.act(async () => {
    release(taskValue(taskOutcomes(25, 1, false)));
    await pending;
  });
  expect(taskValue(reads.latest().readOutcomes!).items).toHaveLength(26);
  expect(taskValue(reads.latest().readOutcomes!).page.hasMore).toBe(false);
  reads.unmount();
});

test.each(['refresh', 'disable', 'mutation'])(
  'late task page cannot survive %s',
  async action => {
    readsMock.mockResolvedValue(taskOutcomes());
    const reads = await renderReads({enabled: true});
    let release!: (value: unknown) => void;
    (loadTasks as jest.Mock).mockReturnValueOnce(
      new Promise(resolve => {
        release = resolve;
      }),
    );
    let pending!: Promise<void>;
    await ReactTestRenderer.act(async () => {
      pending = reads.latest().loadMoreTasks();
    });
    if (action === 'disable') await reads.rerender({enabled: false});
    else if (action === 'mutation') {
      (loadTasks as jest.Mock).mockResolvedValueOnce(
        taskValue(taskOutcomes(100, 1, false)),
      );
      await ReactTestRenderer.act(async () => {
        await reads.latest().refreshTasks();
      });
    } else {
      readsMock.mockResolvedValue(taskOutcomes(100, 1, false));
      await ReactTestRenderer.act(async () => {
        await reads.latest().refreshReads(false);
      });
    }
    await ReactTestRenderer.act(async () => {
      release(taskValue(taskOutcomes(25, 1, false)));
      await pending;
    });
    expect(JSON.stringify(reads.latest().readOutcomes)).not.toContain(
      'task-25',
    );
    expect(reads.latest().tasksLoadingMore).toBe(false);
    reads.unmount();
  },
);

test('task cursor expiry resets once and changed-account pages never append', async () => {
  readsMock.mockResolvedValue(taskOutcomes());
  const reads = await renderReads({enabled: true});
  (loadTasks as jest.Mock).mockResolvedValueOnce(
    taskValue(taskOutcomes(25, 1, false, 8)),
  );
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreTasks();
  });
  expect(taskValue(reads.latest().readOutcomes!).items).toHaveLength(25);
  expect(reads.latest().taskNotice).toContain('Try again');
  (loadTasks as jest.Mock)
    .mockRejectedValueOnce(new TaskCursorExpiredError())
    .mockResolvedValueOnce(taskValue(taskOutcomes(100, 1, false)));
  await ReactTestRenderer.act(async () => {
    await reads.latest().loadMoreTasks();
  });
  expect(
    taskValue(reads.latest().readOutcomes!).items.map(item => item.id),
  ).toEqual(['task-100']);
  expect(reads.latest().taskNotice).toContain('refreshed');
  reads.unmount();
});
