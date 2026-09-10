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

test('old conversations keep GET photo counts and omit empty lists', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'photos-one',
      photos: [{id: 'one'}, {id: 'two'}],
    },
    {
      ...conversation,
      id: 'photos-two',
      photos: [],
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({photoCount: 2});
  expect(result.items[1]).not.toHaveProperty('photoCount');
});

test('old conversations keep wire-non-empty category and omit whitespace', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'category-one',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        category: 'work',
      },
    },
    {
      ...conversation,
      id: 'category-two',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        category: ' \u0085 ',
      },
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({category: 'work'});
  expect(result.items[1]).not.toHaveProperty('category');
});

test('old conversations keep GET source wire values', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'source-one',
      source: 'screenpipe',
    },
    {
      ...conversation,
      id: 'source-two',
      source: 'omi',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({source: 'screenpipe'});
  expect(result.items[1]).toMatchObject({source: 'omi'});
});

test('old conversations keep wire-non-empty emoji and omit whitespace', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'emoji-one',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        emoji: '🚀',
      },
    },
    {
      ...conversation,
      id: 'emoji-two',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        emoji: ' \u0085 ',
      },
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({emoji: '🚀'});
  expect(result.items[1]).not.toHaveProperty('emoji');
});

test('old conversations keep GET captured_at_ms and omit missing values', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'capture-one',
      captured_at_ms: 0,
    },
    {
      ...conversation,
      id: 'capture-two',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]!.capturedAtMs).toBe(0);
  expect(result.items[1]).not.toHaveProperty('capturedAtMs');
  for (const captured_at_ms of [null, -1, 1.5, '1000', 8640000000000001]) {
    await expect(
      loadConversations(backend([{...conversation, captured_at_ms}]).api),
    ).rejects.toThrow('captured_at_ms');
  }
});

test('old bare conversation array preserves nullable metadata and offset pagination', async () => {
  const {api, request} = backend(
    Array.from({length: 50}, (_, i) => ({...conversation, id: `old-${i}`})),
  );
  const first = await loadConversations(api);
  expect(first.items[0]).toMatchObject({
    title: 'Real title',
    summary: 'Actual overview',
    updatedAt: null,
    startedAt: null,
  });
  expect(first.items[0]).not.toHaveProperty('emoji');
  expect(first.items[0]).not.toHaveProperty('photoCount');
  expect(first.items[0]).not.toHaveProperty('category');
  expect(first.items[0]).not.toHaveProperty('capturedAtMs');
  expect(first.apiContract).toBe('omi');
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

test('old memories strip namespaced entity prefixes without inventing provenance digests', async () => {
  const {api} = backend([
    {
      id: 'fact',
      content:
        'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
    },
  ]);
  const result = await loadMemories(api);
  expect(result.apiContract).toBe('omi');
  expect(result.items[0]).toMatchObject({
    title: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    summary: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    searchableText: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    provenance: {
      label: 'entity:qa:000008',
      inputDigest: null,
      outputDigest: null,
      synthesisVersion: null,
    },
  });
});

test('old memories strip namespaced entity prefixes separated by NEXT LINE', async () => {
  const {api} = backend([
    {
      id: 'fact-nel',
      content:
        'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
    },
  ]);
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    title: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    summary: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    searchableText: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    provenance: {
      label: 'entity:qa:000008',
      inputDigest: null,
      outputDigest: null,
      synthesisVersion: null,
    },
  });
});

test('old empty memory content stays searchable instead of a blank row', async () => {
  const {api} = backend([
    {
      id: 'blank',
      content: '',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
    },
  ]);
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    title: '',
    summary: '',
    searchableText: 'Memory text unavailable',
  });
});

test('old memories keep GET ledger slot, playbook body, baseline, and known devices', async () => {
  const {api} = backend([
    {
      id: 'ledger',
      content: 'Prefers concise recaps.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
      slot: 'identity.full_name',
      body: 'Open with the weekly recap.',
      kind: 'document',
      ledger_schema_version: 'knowledge_ledger.v1',
      is_baseline: true,
      primary_capture_device: 'macos_ab12cd34',
    },
    {
      id: 'omitted',
      content: 'Likes walking.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
      slot: ' \t\n',
      body: 'Hidden fact body.',
      kind: 'fact',
      ledger_schema_version: 'knowledge_ledger.v1',
      is_baseline: false,
      primary_capture_device: 'windows_ab12cd34',
    },
  ]);
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    ledgerSlot: 'identity.full_name',
    ledgerBody: 'Open with the weekly recap.',
    isBaseline: true,
    captureDeviceLabel: 'Mac',
  });
  expect(result.items[1]).not.toHaveProperty('ledgerSlot');
  expect(result.items[1]).not.toHaveProperty('ledgerBody');
  expect(result.items[1]).not.toHaveProperty('isBaseline');
  expect(result.items[1]).not.toHaveProperty('captureDeviceLabel');
});

test('old memories name GET locked and omit unlocked rows', async () => {
  const {api} = backend([
    {
      id: 'locked',
      content: 'Prefers concise recaps.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
      is_locked: true,
    },
    {
      id: 'open',
      content: 'Likes walking.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: null,
      is_locked: false,
    },
  ]);
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({locked: true});
  expect(result.items[1]).not.toHaveProperty('locked');
});

test('old memories fail closed for malformed ledger chrome', async () => {
  await expect(
    loadMemories(
      backend([
        {
          id: 'bad-slot',
          content: 'Prefers concise recaps.',
          created_at: '2026-09-07T00:00:00Z',
          conversation_id: null,
          slot: 1,
        },
      ]).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(
      backend([
        {
          id: 'bad-baseline',
          content: 'Prefers concise recaps.',
          created_at: '2026-09-07T00:00:00Z',
          conversation_id: null,
          is_baseline: 'true',
        },
      ]).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
  await expect(
    loadMemories(
      backend([
        {
          id: 'bad-locked',
          content: 'Prefers concise recaps.',
          created_at: '2026-09-07T00:00:00Z',
          conversation_id: null,
          is_locked: 'true',
        },
      ]).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
});

test('old empty task descriptions stay searchable instead of failing the page', async () => {
  const {api} = backend({
    action_items: [
      {id: 'blank', description: '', completed: false},
      {id: 'named', description: 'Call Sam', completed: false},
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items).toEqual([
    expect.objectContaining({
      id: 'blank',
      title: '',
      searchableText: 'Task title unavailable',
    }),
    expect.objectContaining({
      id: 'named',
      title: 'Call Sam',
      searchableText: 'Call Sam',
    }),
  ]);
});

test('old tasks name GET exported platforms and omit missing exports', async () => {
  const {api} = backend({
    action_items: [
      {
        id: 'exported',
        description: 'Call Sam',
        completed: false,
        exported: true,
        export_platform: 'todoist',
      },
      {
        id: 'pending',
        description: 'Write recap',
        completed: false,
        exported: false,
        export_platform: 'todoist',
      },
      {
        id: 'blank-platform',
        description: 'Ship notes',
        completed: false,
        exported: true,
        export_platform: ' \u0085 ',
      },
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items[0]).toMatchObject({
    exportCopy: 'Exported to Todoist',
  });
  expect(result.items[1]).not.toHaveProperty('exportCopy');
  expect(result.items[2]).not.toHaveProperty('exportCopy');
});

test('fails closed for malformed GET task export fields', async () => {
  await expect(
    loadTasks(
      backend({
        action_items: [
          {
            id: 'bad-exported',
            description: 'Call Sam',
            completed: false,
            exported: 'true',
          },
        ],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
  await expect(
    loadTasks(
      backend({
        action_items: [
          {
            id: 'bad-platform',
            description: 'Call Sam',
            completed: false,
            exported: true,
            export_platform: 1,
          },
        ],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
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
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({path: '/v3/memories?limit=50&offset=0'}),
  );
  expect(result.items[0]).toMatchObject({
    title: 'I enjoy walking.',
    citations: [],
    timestamp: 1788739200,
    provenance: {inputDigest: null, outputDigest: null, synthesisVersion: null},
  });
  expect(result.items[0]).not.toHaveProperty('locked');
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
  [
    'conversation photos',
    loadConversations,
    [{...conversation, photos: 'nope'}],
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
