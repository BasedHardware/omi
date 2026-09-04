import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

jest.mock('../src/desktopReadClient', () => {
  const actual = jest.requireActual('../src/desktopReadClient');
  return {...actual, loadDesktopReads: jest.fn()};
});

jest.mock('../src/omiNative', () => ({
  omiBackend: {request: jest.fn()},
  omiNative: undefined,
  omiAuth: undefined,
}));

import {useDesktopReads} from '../src/app/useDesktopReads';
import {loadDesktopReads} from '../src/desktopReadClient';

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

  readsMock.mockResolvedValueOnce(errorOutcomes);
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
