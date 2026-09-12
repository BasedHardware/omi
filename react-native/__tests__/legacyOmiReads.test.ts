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

test('old discarded conversations name GET transcript_segments as the list title', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-speech',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 2,
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-titled',
      discarded: true,
      structured: {title: 'AI title', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Live speech',
          speaker: 'SPEAKER_00',
          is_user: true,
          start: 0,
          end: 1,
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-empty',
      discarded: true,
      structured: {title: 'Kept title', overview: 'Actual overview'},
      transcript_segments: [],
    },
    {
      ...conversation,
      id: 'kept-speech',
      discarded: false,
      transcript_segments: [
        {
          text: 'Should not replace title',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 2,
        },
      ],
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0].title).toBe(
    '[00:00:00 - 00:00:02] Speaker 1: Hello from the recording',
  );
  expect(result.items[1].title).toBe('[00:00:00 - 00:00:01] User: Live speech');
  expect(result.items[2].title).toBe('Kept title');
  expect(result.items[3].title).toBe('Real title');
});

test('old discarded conversations keep GET transcript span seconds when clocks are missing', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-timed',
      discarded: true,
      finished_at: null,
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 120,
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-empty-clocks',
      discarded: true,
      transcript_segments: [],
    },
    {
      ...conversation,
      id: 'kept-timed',
      discarded: false,
      transcript_segments: [
        {
          text: 'Should not become list duration',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 120,
        },
      ],
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({transcriptEndSeconds: 120});
  expect(result.items[1]).not.toHaveProperty('transcriptEndSeconds');
  expect(result.items[2]).not.toHaveProperty('transcriptEndSeconds');
});

test('old discarded conversations name GET transcript start/end numeric strings', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-string-clocks',
      discarded: true,
      finished_at: null,
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: '0',
          end: '120',
        },
      ],
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0].title).toBe(
    '[00:00:00 - 00:02:00] Speaker 1: Hello from the recording',
  );
  expect(result.items[0]).toMatchObject({transcriptEndSeconds: 120});
});

test('old conversations keep GET timestamps Flutter DateTime.tryParse accepts', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'space-created',
      created_at: '2026-09-07 00:00:00Z',
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items.map(row => row.id)).toEqual([
    'space-created',
    'neighbor',
  ]);
  expect(result.items[0]?.createdAt).toBe('2026-09-07T00:00:00.000Z');
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

test('old conversations name empty GET visibility as private instead of hiding neighbors', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'empty-visibility',
      visibility: '',
    },
    {
      ...conversation,
      id: 'unknown-visibility',
      visibility: 'secret',
    },
    {
      ...conversation,
      id: 'public-visibility',
      visibility: 'public',
    },
    {
      ...conversation,
      id: 'shared-visibility',
      visibility: 'shared',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items).toHaveLength(4);
  expect(result.items[0]).toMatchObject({
    id: 'empty-visibility',
    visibility: 'private',
  });
  expect(result.items[1]).toMatchObject({
    id: 'unknown-visibility',
    visibility: 'private',
  });
  expect(result.items[2]).toMatchObject({
    id: 'public-visibility',
    visibility: 'public',
  });
  expect(result.items[3]).toMatchObject({
    id: 'shared-visibility',
    visibility: 'shared',
  });
  await expect(
    loadConversations(backend([{...conversation, visibility: 1}]).api),
  ).rejects.toThrow('Omi text is malformed');
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

test('old memories name empty GET conversation_id as omitted instead of hiding neighbors', async () => {
  const {api} = backend([
    {
      id: 'empty-citation',
      content: 'Prefers concise recaps.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: '',
    },
    {
      id: 'cited',
      content: 'Likes walking.',
      created_at: '2026-09-07T00:00:00Z',
      conversation_id: 'old-conversation',
    },
  ]);
  const result = await loadMemories(api);
  expect(result.items).toHaveLength(2);
  expect(result.items[0]).toMatchObject({
    id: 'empty-citation',
    citations: [],
  });
  expect(result.items[1]).toMatchObject({
    id: 'cited',
    citations: ['old-conversation'],
  });
  await expect(
    loadMemories(
      backend([
        {
          id: 'bad-citation',
          content: 'Prefers concise recaps.',
          created_at: '2026-09-07T00:00:00Z',
          conversation_id: 1,
        },
      ]).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
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

test('old tasks keep GET taskId for chat task_card joins', async () => {
  const {api} = backend({
    action_items: [
      {
        id: 'exported',
        description: 'Call Sam',
        completed: false,
        task_id: 'task-join',
      },
      {
        id: 'aliased',
        description: 'Write recap',
        completed: false,
        taskId: 'task-alias',
      },
      {
        id: 'plain',
        description: 'Ship notes',
        completed: false,
      },
      {
        id: 'blank',
        description: 'Blank task id',
        completed: false,
        task_id: ' \t',
      },
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items[0]).toMatchObject({taskId: 'task-join'});
  expect(result.items[1]).toMatchObject({taskId: 'task-alias'});
  expect(result.items[2]).not.toHaveProperty('taskId');
  expect(result.items[3]).not.toHaveProperty('taskId');
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

test('old tasks name GET sort_order and indent_level integer strings', async () => {
  const {api} = backend({
    action_items: [
      {
        id: 'string-order',
        description: 'Call Alex',
        completed: false,
        sort_order: '-5',
        indent_level: '2',
      },
      {
        id: 'named',
        description: 'Write recap',
        completed: false,
      },
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items[0]).toMatchObject({sortOrder: -5, indentLevel: 2});
  expect(result.items[1]).toMatchObject({sortOrder: 0, indentLevel: 0});
  await expect(
    loadTasks(
      backend({
        action_items: [
          {
            id: 'fraction',
            description: 'Call Alex',
            completed: false,
            sort_order: '1.5',
          },
        ],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadTasks(
      backend({
        action_items: [
          {
            id: 'decimal-string',
            description: 'Call Alex',
            completed: false,
            indent_level: '3.0',
          },
        ],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
});

test('old tasks name GET negative indent_level instead of hiding neighbors', async () => {
  const {api} = backend({
    action_items: [
      {
        id: 'negative-indent',
        description: 'Call Alex',
        completed: false,
        indent_level: -1,
      },
      {
        id: 'named',
        description: 'Write recap',
        completed: false,
      },
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items).toEqual([
    expect.objectContaining({
      id: 'negative-indent',
      title: 'Call Alex',
      indentLevel: -1,
    }),
    expect.objectContaining({id: 'named', title: 'Write recap'}),
  ]);
  const namedStrings = await loadTasks(
    backend({
      action_items: [
        {
          id: 'negative-string',
          description: 'Call Alex',
          completed: false,
          indent_level: '-1',
        },
        {
          id: 'named',
          description: 'Write recap',
          completed: false,
        },
      ],
      has_more: false,
    }).api,
  );
  expect(namedStrings.items).toEqual([
    expect.objectContaining({
      id: 'negative-string',
      title: 'Call Alex',
      indentLevel: -1,
    }),
    expect.objectContaining({id: 'named', title: 'Write recap'}),
  ]);
});

test('old tasks name omitted GET has_more as Flutter false instead of hiding neighbors', async () => {
  const {api} = backend({
    action_items: [
      {id: 'named', description: 'Call Sam', completed: false},
      {id: 'also', description: 'Write recap', completed: true},
    ],
  });
  const result = await loadTasks(api);
  expect(result.items).toEqual([
    expect.objectContaining({id: 'named', title: 'Call Sam'}),
    expect.objectContaining({id: 'also', title: 'Write recap'}),
  ]);
  expect(result.page).toMatchObject({
    complete: true,
    hasMore: false,
    nextCursor: null,
  });
  await expect(
    loadTasks(
      backend({
        action_items: [{id: 'named', description: 'Call Sam', completed: false}],
        has_more: 'true',
      }).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
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

test('does not omit neighboring GET tasks when a provenance id is empty', async () => {
  const {api} = backend({
    action_items: [
      {id: 'kept', description: 'Call Sam', completed: false},
      {
        id: 'empty-provenance',
        description: 'Follow up',
        completed: false,
        provenance: [{kind: 'conversation', id: '', scope: 'canonical'}],
      },
    ],
  });
  const result = await loadTasks(api);
  expect(result.items.map(row => row.id)).toEqual([
    'kept',
    'empty-provenance',
  ]);
  expect(
    result.items.find(row => row.id === 'empty-provenance')?.provenance,
  ).toEqual([JSON.stringify({kind: 'conversation', id: '', scope: 'canonical'})]);
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
