import {
  conversationStructuredEmojiDefaultCopy,
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

function omiMemory(row: Record<string, unknown>) {
  return {
    uid: 'user-1',
    created_at: '2026-09-07T00:00:00Z',
    updated_at: '2026-09-07T00:00:00Z',
    ...row,
  };
}

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

test('old conversations name Flutter ConversationListItem fromJson padded GET latitude instead of remapping to a conversation chip', async () => {
  const neighbor = {
    ...conversation,
    id: 'named',
    structured: {title: 'Neighbor walk', overview: 'Kept neighbor'},
  };
  const row = {
    ...conversation,
    id: 'located',
    structured: {title: 'Market street', overview: 'Located recap'},
  };
  const keptExact = await loadConversations(
    backend([
      {
        ...row,
        geolocation: {latitude: '37.7749', longitude: -122.4194},
      },
      {
        ...row,
        id: 'json',
        geolocation: {latitude: 37.7749, longitude: -122.4194},
      },
      neighbor,
    ]).api,
  );
  expect(keptExact.items.map(item => item.id)).toEqual([
    'located',
    'json',
    'named',
  ]);
  const keptOmitted = await loadConversations(backend([row, neighbor]).api);
  expect(keptOmitted.items.map(item => item.id)).toEqual(['located', 'named']);
  const keptNull = await loadConversations(
    backend([{...row, geolocation: null}, neighbor]).api,
  );
  expect(keptNull.items.map(item => item.id)).toEqual(['located', 'named']);
  const keptMeetingExact = await loadConversations(
    backend([
      {...row, meeting_duration_s: '12.5', meeting_dedup_speech_s: 8},
      neighbor,
    ]).api,
  );
  expect(keptMeetingExact.items.map(item => item.id)).toEqual([
    'located',
    'named',
  ]);
  for (const latitude of [
    '  37.7749  ',
    '37.7749 ',
    '  37.7749',
    '37.7749\n',
    '\u008537.7749',
    ' \t',
  ]) {
    await expect(
      loadConversations(
        backend([
          {
            ...row,
            geolocation: {latitude, longitude: -122.4194},
          },
          neighbor,
        ]).api,
      ),
    ).rejects.toThrow('Omi order is malformed');
  }
  await expect(
    loadConversations(
      backend([
        {
          ...row,
          geolocation: {latitude: 37.7749, longitude: '  -122.4194  '},
        },
        neighbor,
      ]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadConversations(
      backend([
        {
          ...row,
          geolocation: {
            latitude: 37.7749,
            longitude: -122.4194,
            accuracy: '  5.5  ',
          },
        },
        neighbor,
      ]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadConversations(
      backend([{...row, meeting_duration_s: '  12.5  '}, neighbor]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadConversations(
      backend([{...row, meeting_dedup_speech_s: '  8  '}, neighbor]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
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
  expect(result.items[2].title).toBe('');
  expect(result.items[3].title).toBe('Real title');
});

test('old conversations keep GET transcript span seconds when clocks are missing', async () => {
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
          text: 'Flutter list duration uses last segment end',
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
  expect(result.items[2]).toMatchObject({transcriptEndSeconds: 120});
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

test('names Flutter ConversationListItem padded GET start instead of remapping to a clock', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-padded-clocks',
      discarded: true,
      finished_at: null,
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: '  0  ',
          end: '120',
        },
      ],
    },
  ]);
  await expect(loadConversations(api)).rejects.toThrow(
    'Omi transcript is malformed',
  );
});

test('old discarded conversations keep GET transcript_segments when more than 20000', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-long',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: Array.from({length: 20001}, (_, index) => ({
        text: `Speech ${index}`,
        speaker: 'SPEAKER_00',
        is_user: false,
        start: 0,
        end: 1,
      })),
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items.map(row => row.id)).toEqual([
    'discarded-long',
    'neighbor',
  ]);
  expect(result.items[0].title).toContain('Speech 20000');
  expect(result.items[1].title).toBe('Real title');
});

test('old discarded conversations name GET people names on transcript_segments', async () => {
  const conversations = [
    {
      ...conversation,
      id: 'discarded-named',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 2,
          person_id: 'person-alex',
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-unresolved',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Later speech',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
          person_id: 'person-missing',
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-empty-name',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Anonymous empty',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
          person_id: 'person-empty',
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-empty-person',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Anonymous',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
          person_id: null,
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-whitespace-id',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Whitespace id speech',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
          person_id: ' \t',
        },
      ],
    },
    {
      ...conversation,
      id: 'discarded-blank-id',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Blank id speech',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
          person_id: '',
        },
      ],
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ];
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([
          {id: 'person-alex', name: 'Alex Chen'},
          {id: 'person-empty', name: ' \t'},
          {id: ' \t', name: 'Whitespace id'},
          {id: '', name: 'Blank id'},
        ]),
      };
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(conversations),
    };
  });
  const api = {
    request,
    getApiContract: async () => 'omi' as const,
  } as unknown as OmiBackend;
  const result = await loadConversations(api);
  expect(result.items.map(row => row.id)).toEqual([
    'discarded-named',
    'discarded-unresolved',
    'discarded-empty-name',
    'discarded-empty-person',
    'discarded-whitespace-id',
    'discarded-blank-id',
    'neighbor',
  ]);
  expect(result.items[0].title).toBe(
    '[00:00:00 - 00:00:02] Alex Chen: Hello from the recording',
  );
  expect(result.items[1].title).toBe(
    '[00:00:00 - 00:00:01] Speaker 1: Later speech',
  );
  expect(result.items[2].title).toBe(
    '[00:00:00 - 00:00:01]  \t: Anonymous empty',
  );
  expect(result.items[3].title).toBe(
    '[00:00:00 - 00:00:01] Speaker 1: Anonymous',
  );
  expect(result.items[4].title).toBe(
    '[00:00:00 - 00:00:01] Whitespace id: Whitespace id speech',
  );
  expect(result.items[5].title).toBe(
    '[00:00:00 - 00:00:01] Blank id: Blank id speech',
  );
  expect(result.items[6].title).toBe('Real title');
});

test('old discarded conversations keep neighboring titles when people names are unavailable', async () => {
  const conversations = [
    {
      ...conversation,
      id: 'discarded-named',
      discarded: true,
      structured: {title: '', overview: 'Actual overview'},
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 2,
          person_id: 'person-alex',
        },
      ],
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ];
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path === '/v1/users/people?include_speech_samples=false') {
      return {id: 'people', status: 500, body: null};
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(conversations),
    };
  });
  const api = {
    request,
    getApiContract: async () => 'omi' as const,
  } as unknown as OmiBackend;
  const result = await loadConversations(api);
  expect(result.items.map(row => row.id)).toEqual([
    'discarded-named',
    'neighbor',
  ]);
  expect(result.items[0].title).toBe(
    '[00:00:00 - 00:00:02] Speaker 1: Hello from the recording',
  );
  expect(result.items[1].title).toBe('Real title');
});

test('old discarded conversations throw when transcript person_id is present and not a string', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'discarded-person',
      discarded: true,
      transcript_segments: [
        {
          text: 'Hello from the recording',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 2,
          person_id: 1,
        },
      ],
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ]);
  await expect(loadConversations(api)).rejects.toThrow(
    'Omi text is malformed',
  );
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

test('old conversations keep GET timestamps with hour-only offsets Dart DateTime.tryParse accepts', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'hour-offset',
      created_at: '2026-09-07T00:00:00+00',
    },
    {
      ...conversation,
      id: 'neighbor',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items.map(row => row.id)).toEqual([
    'hour-offset',
    'neighbor',
  ]);
  expect(result.items[0]?.createdAt).toBe('2026-09-07T00:00:00.000Z');
});

test('old conversations keep wire-non-empty category and empty GET category', async () => {
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
  expect(result.items[1]).toMatchObject({category: ' \u0085 '});
});

test('old conversations name Flutter omitted GET category as other', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'category-omitted',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
      },
    },
    {
      ...conversation,
      id: 'category-null',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        category: null,
      },
    },
    {
      ...conversation,
      id: 'category-empty',
      structured: {
        title: 'Real title',
        overview: 'Actual overview',
        category: '',
      },
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({category: 'other'});
  expect(result.items[1]).toMatchObject({category: 'other'});
  expect(result.items[2]).not.toHaveProperty('category');
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

test('old conversations keep padded GET source wire values', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'padded-source',
      source: '  screenpipe  ',
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items[0]).toMatchObject({source: '  screenpipe  '});
});

test('old conversations keep wire-non-empty emoji and empty GET emoji', async () => {
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
  expect(result.items[1]).toMatchObject({emoji: ' \u0085 '});
});

test('old conversations name omitted or JSON-null GET structured.emoji as Flutter 🧠', async () => {
  const omitted = await loadConversations(
    backend([
      {
        ...conversation,
        id: 'emoji-omitted',
        structured: {title: 'Real title', overview: 'Actual overview'},
      },
    ]).api,
  );
  expect(omitted.items[0]).toMatchObject({
    emoji: conversationStructuredEmojiDefaultCopy(),
  });
  const jsonNull = await loadConversations(
    backend([
      {
        ...conversation,
        id: 'emoji-null',
        structured: {
          title: 'Real title',
          overview: 'Actual overview',
          emoji: null,
        },
      },
    ]).api,
  );
  expect(jsonNull.items[0]).toMatchObject({
    emoji: conversationStructuredEmojiDefaultCopy(),
  });
  const empty = await loadConversations(
    backend([
      {
        ...conversation,
        id: 'emoji-empty',
        structured: {
          title: 'Real title',
          overview: 'Actual overview',
          emoji: '',
        },
      },
    ]).api,
  );
  expect(empty.items[0]).toMatchObject({emoji: ''});
  await expect(
    loadConversations(
      backend([
        {
          ...conversation,
          id: 'emoji-bad',
          structured: {
            title: 'Real title',
            overview: 'Actual overview',
            emoji: 1,
          },
        },
      ]).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
});

test('names Flutter ConversationListItem empty GET ids instead of omitting neighboring conversations', async () => {
  const {api} = backend([
    {
      ...conversation,
      id: 'kept',
      structured: {title: 'Kept title', overview: 'Actual overview'},
    },
    {
      ...conversation,
      id: '',
      structured: {title: 'Empty id', overview: 'Actual overview'},
    },
    {
      ...conversation,
      id: ' \t',
      structured: {title: 'Whitespace id', overview: 'Actual overview'},
    },
    {
      ...conversation,
      id: '\u0085',
      structured: {title: 'Next line id', overview: 'Actual overview'},
    },
    {
      ...conversation,
      id: '  padded  ',
      structured: {title: 'Padded id', overview: 'Actual overview'},
    },
    {
      ...conversation,
      id: '',
      structured: {title: 'Second empty id', overview: 'Actual overview'},
    },
  ]);
  const result = await loadConversations(api);
  expect(result.items.map(row => ({id: row.id, title: row.title}))).toEqual([
    {id: 'kept', title: 'Kept title'},
    {id: '', title: 'Empty id'},
    {id: ' \t', title: 'Whitespace id'},
    {id: '\u0085', title: 'Next line id'},
    {id: '  padded  ', title: 'Padded id'},
    {id: '', title: 'Second empty id'},
  ]);
  await expect(
    loadConversations(backend([{...conversation, id: undefined}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadConversations(backend([{...conversation, id: null}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadConversations(backend([{...conversation, id: 1}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadConversations(
      backend([
        {...conversation, id: 'same'},
        {...conversation, id: 'same'},
      ]).api,
    ),
  ).rejects.toThrow('Omi IDs are duplicated');
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
    emoji: conversationStructuredEmojiDefaultCopy(),
    category: 'other',
  });
  expect(first.items[0]).not.toHaveProperty('photoCount');
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
  const {api} = backend(
    [
      {
        id: 'fact',
        content:
          'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
    ].map(omiMemory),
  );
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
  const {api} = backend(
    [
      {
        id: 'fact-nel',
        content:
          'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
    ].map(omiMemory),
  );
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
  const {api} = backend(
    [
      {
        id: 'blank',
        content: '',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    title: '',
    summary: '',
    searchableText: '',
  });
});

test('names Flutter MemoryItem empty GET ids instead of omitting neighboring memories', async () => {
  const {api} = backend(
    [
      {
        id: 'kept',
        content: 'Kept title',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
      {
        id: '',
        content: 'Empty id',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
      {
        id: ' \t',
        content: 'Whitespace id',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
      {
        id: '\u0085',
        content: 'Next line id',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
      {
        id: '  padded  ',
        content: 'Padded id',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
      {
        id: '',
        content: 'Second empty id',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items.map(row => ({id: row.id, title: row.title}))).toEqual([
    {id: 'kept', title: 'Kept title'},
    {id: '', title: 'Empty id'},
    {id: ' \t', title: 'Whitespace id'},
    {id: '\u0085', title: 'Next line id'},
    {id: '  padded  ', title: 'Padded id'},
    {id: '', title: 'Second empty id'},
  ]);
  await expect(
    loadMemories(
      backend(
        [{content: 'Omitted id', created_at: '2026-09-07T00:00:00Z'}].map(
          omiMemory,
        ),
      ).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(
      backend(
        [{id: null, content: 'Null id', created_at: '2026-09-07T00:00:00Z'}].map(
          omiMemory,
        ),
      ).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(
      backend(
        [{id: 1, content: 'Numeric id', created_at: '2026-09-07T00:00:00Z'}].map(
          omiMemory,
        ),
      ).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'same',
            content: 'First',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
          {
            id: 'same',
            content: 'Second',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi IDs are duplicated');
});

test('old memories name empty GET conversation_id as omitted instead of hiding neighbors', async () => {
  const {api} = backend(
    [
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
    ].map(omiMemory),
  );
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
      backend(
        [
          {
            id: 'bad-citation',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: 1,
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
});

test('old memories keep GET ledger slot, playbook body, baseline, and known devices', async () => {
  const {api} = backend(
    [
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
        id: 'padded-slot',
        content: 'Prefers padded slots.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        slot: '  identity.full_name  ',
        body: 'Open with the weekly recap.',
        kind: 'document',
        ledger_schema_version: 'knowledge_ledger.v1',
        is_baseline: false,
        primary_capture_device: 'macos_ab12cd34',
      },
      {
        id: 'padded-device',
        content: 'Prefers padded devices.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        slot: 'identity.full_name',
        kind: 'fact',
        ledger_schema_version: 'knowledge_ledger.v1',
        is_baseline: false,
        primary_capture_device: '  macos_ab12cd34',
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
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    ledgerSlot: 'identity.full_name',
    ledgerBody: 'Open with the weekly recap.',
    isBaseline: true,
    captureDeviceLabel: 'Mac',
  });
  expect(result.items[1]).toMatchObject({
    ledgerSlot: '  identity.full_name  ',
    captureDeviceLabel: 'Mac',
  });
  expect(result.items[2]).toMatchObject({
    ledgerSlot: 'identity.full_name',
  });
  expect(result.items[2]).not.toHaveProperty('captureDeviceLabel');
  expect(result.items[3]).not.toHaveProperty('ledgerSlot');
  expect(result.items[3]).not.toHaveProperty('ledgerBody');
  expect(result.items[3]).not.toHaveProperty('isBaseline');
  expect(result.items[3]).not.toHaveProperty('captureDeviceLabel');
});

test('old memories name GET knowledge-ledger History chrome Flutter paints on non-current rows', async () => {
  const {api} = backend(
    [
      {
        id: 'current',
        content: 'Prefers concise recaps.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        kind: 'fact',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
      },
      {
        id: 'rejected',
        content: 'Previous name was Sam.',
        created_at: '2026-09-06T00:00:00Z',
        conversation_id: null,
        kind: 'fact',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'omitted-intent',
        content: 'Used to live in Berlin.',
        created_at: '2026-09-05T00:00:00Z',
        conversation_id: null,
        kind: 'document',
        ledger_schema_version: 'knowledge_ledger.v1',
      },
      {
        id: 'plain',
        content: 'Likes walking.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        user_review: false,
      },
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items[0]).not.toHaveProperty('history');
  expect(result.items[1]).toMatchObject({history: true});
  expect(result.items[2]).toMatchObject({history: true});
  expect(result.items[3]).not.toHaveProperty('history');
});

test('old memories name Flutter MemoryItem padded GET ledger schema and kind instead of remapping to playbook or History chrome', async () => {
  const {api} = backend(
    [
      {
        id: 'exact-playbook',
        content: 'Prefers concise recaps.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: 'document',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
      },
      {
        id: 'padded-schema',
        content: 'Prefers padded schema.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: 'document',
        ledger_schema_version: '  knowledge_ledger.v1  ',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'trailing-schema',
        content: 'Prefers trailing schema.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: 'document',
        ledger_schema_version: 'knowledge_ledger.v1 ',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'next-line-schema',
        content: 'Prefers next-line schema.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: 'document',
        ledger_schema_version: '\u0085knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'padded-kind',
        content: 'Prefers padded kind.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: '  document  ',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'trailing-kind',
        content: 'Prefers trailing kind.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: 'document ',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'next-line-kind',
        content: 'Prefers next-line kind.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
        body: 'Open with the weekly recap.',
        kind: '\u0085document',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'padded-fact',
        content: 'Previous name was Sam.',
        created_at: '2026-09-06T00:00:00Z',
        conversation_id: null,
        kind: '  fact  ',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
      {
        id: 'padded-trigger',
        content: 'Used to live in Berlin.',
        created_at: '2026-09-05T00:00:00Z',
        conversation_id: null,
        kind: '  trigger  ',
        ledger_schema_version: 'knowledge_ledger.v1',
      },
      {
        id: 'exact-history',
        content: 'Previous name was Sam.',
        created_at: '2026-09-06T00:00:00Z',
        conversation_id: null,
        kind: 'fact',
        ledger_schema_version: 'knowledge_ledger.v1',
        intent_backed: true,
        user_review: false,
      },
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({
    ledgerBody: 'Open with the weekly recap.',
  });
  expect(result.items[0]).not.toHaveProperty('history');
  for (const item of result.items.slice(1, 9)) {
    expect(item).not.toHaveProperty('ledgerBody');
    expect(item).not.toHaveProperty('history');
  }
  expect(result.items[9]).toMatchObject({history: true});
  expect(result.items[9]).not.toHaveProperty('ledgerBody');
});

test('old memories name GET locked and omit unlocked rows', async () => {
  const {api} = backend(
    [
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
    ].map(omiMemory),
  );
  const result = await loadMemories(api);
  expect(result.items[0]).toMatchObject({locked: true});
  expect(result.items[1]).not.toHaveProperty('locked');
});

test('old memories fail closed for malformed ledger chrome', async () => {
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'bad-slot',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
            slot: 1,
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'bad-baseline',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
            is_baseline: 'true',
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'bad-locked',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
            is_locked: 'true',
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'bad-intent',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
            intent_backed: 'true',
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
  await expect(
    loadMemories(
      backend(
        [
          {
            id: 'bad-review',
            content: 'Prefers concise recaps.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
            user_review: 'false',
          },
        ].map(omiMemory),
      ).api,
    ),
  ).rejects.toThrow('Omi boolean is malformed');
});

test('old memories name Flutter MemoriesPage fromJson omitted GET uid and updated_at', async () => {
  const row = omiMemory({
    id: 'fact',
    content: 'Prefers concise recaps.',
    conversation_id: null,
  });
  await expect(
    loadMemories(backend([{...row, uid: undefined}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(backend([{...row, uid: 1}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(backend([{...row, updated_at: undefined}]).api),
  ).rejects.toThrow('Omi timestamp is malformed');
  await expect(
    loadMemories(backend([{...row, updated_at: null}]).api),
  ).rejects.toThrow('Omi timestamp is malformed');
  await expect(
    loadMemories(backend([{...row, updated_at: ''}]).api),
  ).rejects.toThrow('Omi timestamp is malformed');
  await expect(
    loadMemories(backend([{...row, updated_at: 'not-a-date'}]).api),
  ).rejects.toThrow('Omi timestamp is malformed');
  await expect(
    loadMemories(backend([{...row, created_at: undefined}]).api),
  ).rejects.toThrow('Omi timestamp is malformed');
  const kept = await loadMemories(backend([{...row, uid: ''}]).api);
  expect(kept.items[0]).toMatchObject({id: 'fact'});
});

test('old memories name Flutter MemoriesPage fromJson invalid GET evidence', async () => {
  const row = omiMemory({
    id: 'fact',
    content: 'Prefers concise recaps.',
    conversation_id: null,
  });
  await expect(
    loadMemories(backend([{...row, evidence: 'bad'}]).api),
  ).rejects.toThrow('Omi list is malformed');
  await expect(
    loadMemories(backend([{...row, evidence: [{title: 'Calendar'}]}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(backend([{...row, category: 1}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(backend([{...row, category: null}]).api),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadMemories(backend([{...row, is_locked: null}]).api),
  ).rejects.toThrow('Omi boolean is malformed');
  const kept = await loadMemories(
    backend([
      {
        ...row,
        evidence: [{evidence_id: 'ev-1', independence_group: 'g1'}],
        category: 'interesting',
        app_id: null,
        tags: null,
      },
    ]).api,
  );
  expect(kept.items).toHaveLength(1);
  expect(kept.items[0]).toMatchObject({id: 'fact'});
  expect(kept.items[0]).not.toHaveProperty('evidence');
});

test('old memories name Flutter MemoriesPage fromJson padded GET capture_confidence instead of remapping to a memory chip', async () => {
  const neighbor = omiMemory({
    id: 'named',
    content: 'Likes walking.',
    conversation_id: null,
  });
  const row = omiMemory({
    id: 'fact',
    content: 'Prefers concise recaps.',
    conversation_id: null,
  });
  const keptExact = await loadMemories(
    backend([
      {...row, capture_confidence: '0.9'},
      {...row, id: 'json', capture_confidence: 0.9},
      neighbor,
    ]).api,
  );
  expect(keptExact.items.map(item => item.id)).toEqual([
    'fact',
    'json',
    'named',
  ]);
  const keptOmitted = await loadMemories(backend([row, neighbor]).api);
  expect(keptOmitted.items.map(item => item.id)).toEqual(['fact', 'named']);
  const keptNull = await loadMemories(
    backend([{...row, capture_confidence: null}, neighbor]).api,
  );
  expect(keptNull.items.map(item => item.id)).toEqual(['fact', 'named']);
  for (const capture_confidence of [
    '  0.9  ',
    '0.9 ',
    '  0.9',
    '0.9\n',
    '\u00850.9',
    ' \t',
  ]) {
    await expect(
      loadMemories(
        backend([{...row, capture_confidence}, neighbor]).api,
      ),
    ).rejects.toThrow('Omi order is malformed');
  }
  await expect(
    loadMemories(
      backend([{...row, currency: '  1.5  '}, neighbor]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadMemories(
      backend([{...row, half_life_days: '  7  '}, neighbor]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadMemories(
      backend([{...row, veracity: '  0.8  '}, neighbor]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadMemories(
      backend([
        {
          ...row,
          evidence: [
            {
              evidence_id: 'ev-1',
              independence_group: 'g1',
              capture_confidence: '  0.5  ',
            },
          ],
        },
        neighbor,
      ]).api,
    ),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadMemories(backend([{...row, capture_confidence: 'nope'}]).api),
  ).rejects.toThrow('Omi order is malformed');
  await expect(
    loadMemories(backend([{...row, capture_confidence: ''}]).api),
  ).rejects.toThrow('Omi order is malformed');
});

test('names Flutter ActionItemsPage empty GET ids instead of omitting neighboring tasks', async () => {
  const {api} = backend({
    action_items: [
      {id: 'kept', description: 'Kept title', completed: false},
      {id: '', description: 'Empty id', completed: false},
      {id: ' \t', description: 'Whitespace id', completed: false},
      {id: '\u0085', description: 'Next line id', completed: false},
      {id: '  padded  ', description: 'Padded id', completed: false},
      {id: '', description: 'Second empty id', completed: false},
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items.map(row => ({id: row.id, title: row.title}))).toEqual([
    {id: 'kept', title: 'Kept title'},
    {id: '', title: 'Empty id'},
    {id: ' \t', title: 'Whitespace id'},
    {id: '\u0085', title: 'Next line id'},
    {id: '  padded  ', title: 'Padded id'},
    {id: '', title: 'Second empty id'},
  ]);
  await expect(
    loadTasks(
      backend({
        action_items: [{description: 'Omitted id', completed: false}],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadTasks(
      backend({
        action_items: [{id: null, description: 'Null id', completed: false}],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadTasks(
      backend({
        action_items: [{id: 1, description: 'Numeric id', completed: false}],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi text is malformed');
  await expect(
    loadTasks(
      backend({
        action_items: [
          {id: 'same', description: 'First', completed: false},
          {id: 'same', description: 'Second', completed: false},
        ],
        has_more: false,
      }).api,
    ),
  ).rejects.toThrow('Omi IDs are duplicated');
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
      searchableText: '',
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

test('old tasks name Flutter ActionItemsPage empty GET export_platform', async () => {
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
      {
        id: 'padded-platform',
        description: 'Padded platform',
        completed: false,
        exported: true,
        export_platform: '  todoist  ',
      },
      {
        id: 'empty-platform',
        description: 'Empty platform',
        completed: false,
        exported: true,
        export_platform: '',
      },
      {
        id: 'omitted-platform',
        description: 'Omitted platform',
        completed: false,
        exported: true,
      },
    ],
    has_more: false,
  });
  const result = await loadTasks(api);
  expect(result.items[0]).toMatchObject({
    exportCopy: 'Exported to Todoist',
  });
  expect(result.items[1]).not.toHaveProperty('exportCopy');
  expect(result.items[2]).toMatchObject({
    exportCopy: 'Exported to  \u0085 ',
  });
  expect(result.items[3]).toMatchObject({
    exportCopy: 'Exported to   todoist  ',
  });
  expect(result.items[4]).toMatchObject({
    exportCopy: 'Exported to ',
  });
  expect(result.items[5]).not.toHaveProperty('exportCopy');
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
  const {api, request} = backend(
    [
      {
        id: 'fact',
        content: 'I enjoy walking.',
        created_at: '2026-09-07T00:00:00Z',
        conversation_id: null,
      },
    ].map(omiMemory),
  );
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

test('old memories name GET ledger-history rows Flutter merges onto the current list', async () => {
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path?.includes('ledger-history')) {
      return {
        id: 'read',
        status: 200,
        body: JSON.stringify(
          [
            {
              id: 'closed-fact',
              content: 'Previous name was Sam.',
              created_at: '2026-09-06T00:00:00Z',
              conversation_id: null,
            },
            {
              id: 'fact',
              content: 'Duplicate of the current row.',
              created_at: '2026-09-07T00:00:00Z',
              conversation_id: null,
            },
          ].map(omiMemory),
        ),
      };
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(
        [
          {
            id: 'fact',
            content: 'I enjoy walking.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ),
    };
  });
  const api = {
    getApiContract: async () => 'omi',
    request,
  } as unknown as OmiBackend;
  const result = await loadMemories(api);
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      path: '/v3/memories/ledger-history?limit=500&offset=0',
    }),
  );
  expect(result.items.map(row => row.id)).toEqual(['fact', 'closed-fact']);
  expect(result.items[1]).toMatchObject({
    title: 'Previous name was Sam.',
    timestamp: 1788652800,
  });
  expect(result.page.nextCursor).toBeNull();
});

test('old memories keep the current list when ledger-history is unavailable', async () => {
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path?.includes('ledger-history')) {
      return {id: 'read', status: 404, body: '{"detail":"not found"}'};
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(
        [
          {
            id: 'fact',
            content: 'I enjoy walking.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ),
    };
  });
  const api = {
    getApiContract: async () => 'omi',
    request,
  } as unknown as OmiBackend;
  const result = await loadMemories(api);
  expect(result.items.map(row => row.id)).toEqual(['fact']);
});

test('old memories keep the current list when ledger-history 200 cannot project', async () => {
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path?.includes('ledger-history')) {
      return {id: 'read', status: 200, body: '{"memories":[]}'};
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(
        [
          {
            id: 'fact',
            content: 'I enjoy walking.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ),
    };
  });
  const api = {
    getApiContract: async () => 'omi',
    request,
  } as unknown as OmiBackend;
  const result = await loadMemories(api);
  expect(result.items.map(row => row.id)).toEqual(['fact']);
});

function ledgerHistoryRow(id: string) {
  return omiMemory({
    id,
    content: `History ${id}`,
    created_at: '2026-09-06T00:00:00Z',
    conversation_id: null,
  });
}

function ledgerHistoryPage(offset: number, count: number) {
  return Array.from({length: count}, (_, index) =>
    ledgerHistoryRow(`hist-${offset + index}`),
  );
}

test('old memories name Flutter ledger-history 10-page cap as partial', async () => {
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path?.includes('ledger-history')) {
      const offset = Number(
        new URL(`https://omi.test${input.path}`).searchParams.get('offset'),
      );
      return {
        id: 'read',
        status: 200,
        body: JSON.stringify(ledgerHistoryPage(offset, 500)),
      };
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(
        [
          {
            id: 'fact',
            content: 'I enjoy walking.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ),
    };
  });
  const api = {
    getApiContract: async () => 'omi',
    request,
  } as unknown as OmiBackend;
  const result = await loadMemories(api);
  expect(
    request.mock.calls.filter(([input]: [{path?: string}]) =>
      input.path?.includes('ledger-history'),
    ),
  ).toHaveLength(10);
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      path: '/v3/memories/ledger-history?limit=500&offset=4500',
    }),
  );
  expect(result.items).toHaveLength(5001);
  expect(result.ledgerHistoryTruncated).toBe(true);
  expect(result.page.nextCursor).toBeNull();
});

test('old memories omit ledger-history partial chrome before the Flutter 10-page cap', async () => {
  const request = jest.fn(async (input: {path?: string}) => {
    if (input.path?.includes('ledger-history')) {
      const offset = Number(
        new URL(`https://omi.test${input.path}`).searchParams.get('offset'),
      );
      return {
        id: 'read',
        status: 200,
        body: JSON.stringify(
          ledgerHistoryPage(offset, offset === 4500 ? 12 : 500),
        ),
      };
    }
    return {
      id: 'read',
      status: 200,
      body: JSON.stringify(
        [
          {
            id: 'fact',
            content: 'I enjoy walking.',
            created_at: '2026-09-07T00:00:00Z',
            conversation_id: null,
          },
        ].map(omiMemory),
      ),
    };
  });
  const api = {
    getApiContract: async () => 'omi',
    request,
  } as unknown as OmiBackend;
  const result = await loadMemories(api);
  expect(
    request.mock.calls.filter(([input]: [{path?: string}]) =>
      input.path?.includes('ledger-history'),
    ),
  ).toHaveLength(10);
  expect(result.items).toHaveLength(1 + 9 * 500 + 12);
  expect(result).not.toHaveProperty('ledgerHistoryTruncated');
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
  ['memory content', loadMemories, [{id: 'fact', content: 42}].map(omiMemory)],
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

test('minimal old memories fetch additional offset pages', async () => {
  const {api, request} = backend(
    Array.from({length: 50}, (_, i) =>
      omiMemory({
        id: `fact-${i}`,
        content: `Fact ${i}`,
      }),
    ),
  );
  const first = await loadMemories(api);
  expect(first.items[0]).toMatchObject({timestamp: 1788739200, citations: []});
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
