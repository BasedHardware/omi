import {
  conversationGroupLabel,
  loadConversations,
  loadDesktopReads,
  loadMemories,
  loadTasks,
  parseMemoryText,
  taskGroup,
} from '../src/desktopReadClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';

const page = (items: unknown[], completenessVersion: string) => ({
  contractVersion: '1.0.0',
  accountEpoch: 7,
  items,
  window: {
    status: 'complete',
    complete: true,
    hasMore: false,
    nextCursor: null,
  },
  completeness: {
    version: completenessVersion,
    status: 'complete',
    reasons: [],
  },
  absence: items.length === 0 ? {kind: 'query_gap'} : null,
});

const conversation = {
  id: 'conversation-1',
  structured: {title: 'Morning walk', overview: 'Discussed the launch.'},
  created_at: '2026-08-14T01:00:00.000Z',
  updated_at: '2026-08-14T02:00:00.000Z',
  started_at: '2026-08-14T01:00:00.000Z',
  finished_at: '2026-08-14T01:30:00.000Z',
  source: 'omi',
  status: 'completed',
  discarded: false,
  starred: true,
  visibility: 'private',
  is_locked: false,
  folder_id: null,
};

const memory = {
  id: 'memory1_abc',
  text: 'The launch is Friday.',
  citations: ['citation-v1:launch'],
  provenance: {
    synthesisVersion: 'synthesis-v1',
    inputDigest: 'a'.repeat(64),
    outputDigest: 'b'.repeat(64),
  },
  updatedAt: 1785900200,
};

const task = {
  id: 'task1_abc',
  description: 'Prepare launch notes',
  completed: false,
  completedAt: null,
  dueAt: 1786000000,
  owner: null,
  source: 'assistant',
  provenance: ['assistant:summarizer-v3'],
  sortOrder: 1.5,
  indentLevel: 0,
  createdAt: 1785900000,
  updatedAt: 1785900100,
  revision: 'c'.repeat(64),
};

function backendFor(
  responder: (request: NativeHttpRequest) => {
    status: number;
    body: string | null;
  },
): OmiBackend {
  return {
    request: async request => ({id: request.id, ...responder(request)}),
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
}

test('loads and normalizes all three exact desktop read routes', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    if (request.path.startsWith('/v1/conversations')) {
      return {status: 200, body: JSON.stringify([conversation])};
    }
    if (request.path.startsWith('/v1/memories')) {
      return {
        status: 200,
        body: JSON.stringify(page([memory], 'recall-completeness-v1')),
      };
    }
    return {
      status: 200,
      body: JSON.stringify(page([task], 'tasks-completeness-v1')),
    };
  });

  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'conversation',
          id: 'conversation-1',
          title: 'Morning walk',
          summary: 'Discussed the launch.',
          searchableText: 'Morning walk\nDiscussed the launch.',
          createdAt: '2026-08-14T01:00:00.000Z',
          updatedAt: '2026-08-14T02:00:00.000Z',
          startedAt: '2026-08-14T01:00:00.000Z',
          finishedAt: '2026-08-14T01:30:00.000Z',
          status: 'completed',
          source: 'omi',
          visibility: 'private',
          folderId: null,
          locked: false,
          discarded: false,
        }),
      ],
      page: expect.objectContaining({complete: true, hasMore: false}),
    },
  });
  expect(result.memories).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'memory',
          id: 'memory1_abc',
          searchableText: 'The launch is Friday.\ncitation-v1:launch',
          timestamp: 1785900200,
        }),
      ],
      page: expect.objectContaining({completenessStatus: 'complete'}),
    },
  });
  expect(result.tasks).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'task',
          id: 'task1_abc',
          title: 'Prepare launch notes',
          summary: 'Due 1786000000',
        }),
      ],
      page: expect.objectContaining({completenessStatus: 'complete'}),
      accountEpoch: 7,
    },
  });
  expect(paths.sort()).toEqual(
    [
      '/v1/conversations?limit=50&offset=0',
      '/v1/memories?limit=50',
      '/v1/tasks',
    ].sort(),
  );
});

test('groups validated UTC conversation timestamps by local calendar day', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  expect(
    conversationGroupLabel(new Date(2026, 7, 14, 1, 0).toISOString(), now),
  ).toBe('Today');
  expect(
    conversationGroupLabel(new Date(2026, 7, 13, 23, 0).toISOString(), now),
  ).toBe('Yesterday');
  expect(
    conversationGroupLabel(new Date(2026, 7, 10, 12, 0).toISOString(), now),
  ).toBe(
    new Date(2026, 7, 10, 12, 0).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }),
  );
});

test('preserves absent memory timestamps without inventing an order', async () => {
  const result = await loadMemories(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        page([{...memory, updatedAt: undefined}], 'recall-completeness-v1'),
      ),
    })),
  );
  expect(result.items[0].timestamp).toBeNull();
});

test('separates a machine slug from visible memory text', () => {
  expect(parseMemoryText('quiet-river-lantern: The launch is Friday.')).toEqual(
    {
      body: 'The launch is Friday.',
      provenanceLabel: 'quiet-river-lantern',
    },
  );
  expect(parseMemoryText('A normal memory: with punctuation.')).toEqual({
    body: 'A normal memory: with punctuation.',
    provenanceLabel: null,
  });
});

test('separates a namespaced entity id from visible memory text', () => {
  expect(
    parseMemoryText(
      'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
    ),
  ).toEqual({
    body: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    provenanceLabel: 'entity:qa:000008',
  });
});

test.each([
  ['conversations', loadConversations, JSON.stringify({items: []})],
  [
    'memories',
    loadMemories,
    JSON.stringify(page([{...memory, text: null}], 'recall-completeness-v1')),
  ],
  [
    'tasks',
    loadTasks,
    JSON.stringify(
      page([{...task, completed: 'false'}], 'tasks-completeness-v1'),
    ),
  ],
])('fails closed for malformed %s payloads', async (_label, load, body) => {
  const backend = backendFor(() => ({status: 200, body}));
  await expect(load(backend)).rejects.toThrow(/malformed/);
});

test.each([
  ['conversations', loadConversations],
  ['memories', loadMemories],
  ['tasks', loadTasks],
])(
  'surfaces non-success %s reads without consuming the body',
  async (_label, load) => {
    const backend = backendFor(() => ({status: 503, body: '{"items":[]}'}));
    await expect(load(backend)).rejects.toThrow('failed (503)');
  },
);

test('rejects a malformed page envelope before projecting items', async () => {
  const malformed = {
    ...page([], 'recall-completeness-v1'),
    window: {complete: true},
  };
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(malformed),
  }));
  await expect(loadMemories(backend)).rejects.toThrow(
    'window status is malformed',
  );
});

test('preserves a cursor-backed multi-page memory window', async () => {
  const paths: string[] = [];
  const response = {
    ...page([memory], 'recall-completeness-v1'),
    window: {
      status: 'more',
      complete: false,
      hasMore: true,
      nextCursor: 'cursor-2',
    },
  };
  const backend = backendFor(request => {
    paths.push(request.path);
    return {status: 200, body: JSON.stringify(response)};
  });

  await expect(loadMemories(backend, 'opaque/+ cursor=')).resolves.toEqual({
    items: [expect.objectContaining({id: 'memory1_abc'})],
    page: {
      windowStatus: 'more',
      complete: false,
      hasMore: true,
      nextCursor: 'cursor-2',
      completenessStatus: 'complete',
      reasons: [],
    },
  });
  expect(paths).toEqual([
    '/v1/memories?limit=50&cursor=opaque%2F%2B%20cursor%3D',
  ]);
});

test('rejects an empty memory cursor before issuing a read', async () => {
  const backend = backendFor(() => {
    throw new Error('unexpected request');
  });
  await expect(loadMemories(backend, '')).rejects.toThrow(
    'Memory cursor is malformed',
  );
});

test('preserves an incomplete task projection and its reasons', async () => {
  const response = {
    ...page([task], 'tasks-completeness-v1'),
    window: {
      status: 'incomplete',
      complete: false,
      hasMore: false,
      nextCursor: null,
    },
    completeness: {
      version: 'tasks-completeness-v1',
      status: 'incomplete',
      reasons: ['pending_writes'],
    },
  };
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(response),
  }));

  await expect(loadTasks(backend)).resolves.toEqual({
    items: [expect.objectContaining({id: 'task1_abc'})],
    page: {
      windowStatus: 'incomplete',
      complete: false,
      hasMore: false,
      nextCursor: null,
      completenessStatus: 'incomplete',
      reasons: ['pending_writes'],
    },
    accountEpoch: 7,
  });
});

test('groups task epochs by deterministic UTC day boundaries', () => {
  const now = Date.UTC(2026, 7, 14, 23, 30) / 1000;
  expect(taskGroup(Date.UTC(2026, 7, 14, 0, 0) / 1000, now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 13, 0, 0) / 1000, now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 15, 0, 0) / 1000, now)).toBe('Tomorrow');
  expect(taskGroup(Date.UTC(2026, 7, 16, 0, 0) / 1000, now)).toBe('Later');
  expect(taskGroup(null, now)).toBe('Later');
});

test('accepts an omitted account epoch and retains a null task revision', async () => {
  const response = page([{...task, revision: null}], 'tasks-completeness-v1');
  delete (response as {accountEpoch?: number}).accountEpoch;
  const result = await loadTasks(
    backendFor(() => ({status: 200, body: JSON.stringify(response)})),
  );
  expect(result.accountEpoch).toBeNull();
  expect(result.items[0]).toEqual(
    expect.objectContaining({
      owner: null,
      source: 'assistant',
      provenance: ['assistant:summarizer-v3'],
      indentLevel: 0,
      revision: null,
    }),
  );
});

test('marks a full conversation window as potentially incomplete', async () => {
  const conversations = Array.from({length: 50}, (_, index) => ({
    ...conversation,
    id: `conversation-${index}`,
  }));
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(conversations),
  }));

  const result = await loadConversations(backend);
  expect(result.items).toHaveLength(50);
  expect(result.page).toEqual({
    windowStatus: 'unknown',
    complete: false,
    hasMore: true,
    nextCursor: null,
    completenessStatus: 'unknown',
    reasons: ['limit_reached'],
  });
});

test('keeps nullable conversation times while rejecting invalid metadata', async () => {
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify([
      {...conversation, started_at: null, finished_at: null},
    ]),
  }));

  await expect(loadConversations(backend)).resolves.toMatchObject({
    items: [
      expect.objectContaining({
        startedAt: null,
        finishedAt: null,
        status: 'completed',
        locked: false,
        discarded: false,
      }),
    ],
  });

  const malformed = backendFor(() => ({
    status: 200,
    body: JSON.stringify([{...conversation, updated_at: 'not-a-time'}]),
  }));
  await expect(loadConversations(malformed)).rejects.toThrow(
    'updated_at is malformed',
  );
});

test('retains successful domains when one desktop read fails', async () => {
  const backend = backendFor(request => {
    if (request.path.startsWith('/v1/conversations')) {
      return {status: 503, body: null};
    }
    if (request.path.startsWith('/v1/memories')) {
      return {
        status: 200,
        body: JSON.stringify(page([memory], 'recall-completeness-v1')),
      };
    }
    return {
      status: 200,
      body: JSON.stringify(page([task], 'tasks-completeness-v1')),
    };
  });

  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'error',
    error: 'desktop-conversations-read failed (503)',
  });
  expect(result.memories).toEqual(expect.objectContaining({status: 'success'}));
  expect(result.tasks).toEqual(expect.objectContaining({status: 'success'}));
});
