import {
  loadConversations,
  loadMemories,
  loadTasks,
} from '../src/desktopReadClient';
import type {OmiBackend} from '../src/omiNative';

function backend(value: unknown, contract: 'omi' | 'canonical' = 'omi') {
  const request = jest.fn(async () => ({
    id: 'read',
    status: 200,
    body: JSON.stringify(value),
  }));
  return {
    api: {
      request,
      getApiContract: async () => contract,
    } as unknown as OmiBackend,
    request,
  };
}
const conversation = {
  id: 'old-conversation',
  created_at: '2026-09-07T00:00:00Z',
  updated_at: null,
  started_at: null,
  finished_at: null,
  structured: {title: 'Real title', overview: 'Actual overview'},
  source: null,
  status: 'completed',
  is_locked: false,
  discarded: false,
  folder_id: null,
};

test('old bare conversation array preserves nullable metadata and offset pagination', async () => {
  const {api, request} = backend(
    Array.from({length: 50}, (_, i) => ({...conversation, id: `old-${i}`})),
  );
  const first = await loadConversations(api);
  expect(first.apiContract).toBe('omi');
  expect(first.items[0]).toMatchObject({
    title: 'Real title',
    summary: 'Actual overview',
    updatedAt: null,
    startedAt: null,
  });
  expect(first.page).toMatchObject({
    complete: false,
    nextCursor: 'omi-offset:50',
    hasMore: true,
  });
  await loadConversations(api, first.page.nextCursor);
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({path: '/v1/conversations?limit=50&offset=50'}),
  );
});

test('old memories use v3 content without manufacturing canonical provenance', async () => {
  const {api, request} = backend([
    {
      id: 'fact',
      content: 'I enjoy walking.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
    },
  ]);
  const result = await loadMemories(api);
  expect(result.apiContract).toBe('omi');
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({path: '/v3/memories?limit=50&offset=0'}),
  );
  expect(result.items[0]).toMatchObject({
    title: 'I enjoy walking.',
    citations: [],
    timestamp: 1788739200,
    provenance: {inputDigest: null, outputDigest: null, synthesisVersion: null},
  });
  expect(result.page.completenessStatus).toBe('unknown');
});

test('old task wrapper preserves dates in milliseconds, nullable epochs and source evidence', async () => {
  const evidence = {
    kind: 'conversation',
    id: 'conversation-one',
    scope: 'canonical',
  };
  const {api, request} = backend({
    action_items: [
      {
        id: 'task',
        description: 'Call Alex',
        completed: false,
        due_at: '2026-09-07T01:00:00Z',
        created_at: null,
        updated_at: null,
        completed_at: null,
        provenance: [evidence],
        sort_order: -5,
      },
    ],
    has_more: true,
    truncated: false,
  });
  const result = await loadTasks(api);
  expect(result).toMatchObject({accountEpoch: null, apiContract: 'omi'});
  expect(result.items[0]).toMatchObject({
    createdAt: null,
    updatedAt: null,
    revision: null,
    dueAt: Date.parse('2026-09-07T01:00:00Z'),
    provenance: [JSON.stringify(evidence)],
    sortOrder: -5,
  });
  await loadTasks(api, result.page.nextCursor);
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({path: '/v1/action-items?limit=50&offset=1'}),
  );
});

test('truncated old task scan remains incomplete without advancing an unsafe offset', async () => {
  const {api} = backend({
    action_items: [{id: 'task', description: '', completed: true}],
    has_more: true,
    truncated: true,
  });
  const result = await loadTasks(api);
  expect(result.page).toMatchObject({
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'incomplete',
  });
});

test.each([
  ['conversation array', loadConversations, {items: []}],
  [
    'conversation date',
    loadConversations,
    [{...conversation, created_at: 'bad'}],
  ],
  ['memory content', loadMemories, [{id: 'fact', content: 42}]],
  [
    'task completion',
    loadTasks,
    {
      action_items: [{id: 'task', description: 'x', completed: 'false'}],
      has_more: false,
    },
  ],
  [
    'duplicate rows',
    loadTasks,
    {
      action_items: [
        {id: 'same', description: 'a', completed: false},
        {id: 'same', description: 'b', completed: false},
      ],
      has_more: false,
    },
  ],
] as const)('rejects malformed old %s', async (_label, load, value) => {
  await expect(load(backend(value).api)).rejects.toThrow();
});

test('contract selection never falls back from canonical validation to legacy arrays', async () => {
  const {api, request} = backend([conversation], 'canonical');
  await expect(loadConversations(api)).rejects.toThrow();
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({path: '/v1/conversations?limit=50'}),
  );
});

test('rejects cross-contract and unbounded offset cursors before old transport', async () => {
  const {api, request} = backend([]);
  for (const cursor of [
    'canonical-signed',
    'omi-offset:-1',
    'omi-offset:9007199254740991',
  ]) {
    await expect(loadMemories(api, cursor)).rejects.toThrow();
  }
  expect(request).not.toHaveBeenCalled();
});

test('minimal old memories retain unknown time and fetch additional offset pages', async () => {
  const {api, request} = backend(
    Array.from({length: 50}, (_, i) => ({
      id: `fact-${i}`,
      content: `Fact ${i}`,
    })),
  );
  const first = await loadMemories(api);
  expect(first.items[0]).toMatchObject({timestamp: null, citations: []});
  await loadMemories(api, first.page.nextCursor);
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({path: '/v3/memories?limit=50&offset=50'}),
  );
});

test('empty completed old task response is distinct from an incomplete empty scan', async () => {
  const completed = await loadTasks(
    backend({action_items: [], has_more: false}).api,
  );
  expect(completed.page).toMatchObject({complete: true, hasMore: false});
  const partial = await loadTasks(
    backend({action_items: [], has_more: true, truncated: true}).api,
  );
  expect(partial.page).toMatchObject({complete: false, nextCursor: null});
});

test.each([loadConversations, loadMemories, loadTasks])(
  'old read preserves selected contract when transport changes before dispatch',
  async load => {
    const request = jest.fn(async (input: {expectedApiContract?: string}) => {
      expect(input.expectedApiContract).toBe('omi');
      throw Object.assign(new Error('Backend changed'), {
        code: 'OMI_HTTP_BACKEND_CHANGED',
      });
    });
    const api = {
      getApiContract: async () => 'omi',
      request,
    } as unknown as OmiBackend;
    await expect(load(api)).rejects.toMatchObject({
      code: 'OMI_HTTP_BACKEND_CHANGED',
    });
    expect(request).toHaveBeenCalledTimes(1);
  },
);
