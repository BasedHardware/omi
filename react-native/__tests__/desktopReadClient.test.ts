import {
  loadConversations,
  loadDesktopReads,
  loadMemories,
  loadTasks,
} from '../src/desktopReadClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';

const page = (items: unknown[], completenessVersion: string) => ({
  contractVersion: '1.0.0',
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
    generationEvents: async () => '',
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

  await expect(loadDesktopReads(backend)).resolves.toEqual([
    expect.objectContaining({
      kind: 'conversation',
      id: 'conversation-1',
      title: 'Morning walk',
      summary: 'Discussed the launch.',
      searchableText: 'Morning walk\nDiscussed the launch.',
    }),
    expect.objectContaining({
      kind: 'memory',
      id: 'memory1_abc',
      searchableText: 'The launch is Friday.',
    }),
    expect.objectContaining({
      kind: 'task',
      id: 'task1_abc',
      title: 'Prepare launch notes',
      summary: 'Due 1786000000',
    }),
  ]);
  expect(paths.sort()).toEqual(
    [
      '/v1/conversations?limit=50&offset=0',
      '/v1/memories?limit=50',
      '/v1/tasks',
    ].sort(),
  );
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
