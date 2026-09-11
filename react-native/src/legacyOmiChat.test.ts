import {
  omiHistoryOffset,
  parseOmiChatStream,
  parseOmiHistory,
} from './legacyOmiChat';

const message = (id: string, sender = 'ai', text = 'Hello 世界') => ({
  id,
  sender,
  text,
  created_at: '2026-09-07T01:02:03Z',
  type: 'text',
});

test('old newest-first history reverses and advances only its offset cursor', () => {
  const rows = Array.from({length: 50}, (_, index) =>
    message(String(50 - index)),
  );
  const page = parseOmiHistory(JSON.stringify(rows), 50);
  expect(page.messages[0].id).toBe('1');
  expect(page.olderCursor).toBe('omi-offset:100');
  expect(omiHistoryOffset(page.olderCursor!)).toBe(100);
  expect(parseOmiHistory('[]', 100).hasOlder).toBe(false);
  expect(() => omiHistoryOffset('canonical-token')).toThrow();
  expect(() => parseOmiHistory('{}', 0)).toThrow();
});

test('old custom done frame decodes Unicode and actual message identity without claiming generation success', () => {
  const terminal = Buffer.from(JSON.stringify(message('server-id'))).toString(
    'base64',
  );
  const result = parseOmiChatStream(
    `data: partial\n\nerror: transient\n\ndone: ${terminal}\n\n`,
  );
  expect(result).toMatchObject({
    id: 'server-id',
    text: 'Hello 世界',
    generationOutcome: null,
  });
  expect(() => parseOmiChatStream('data: incomplete\n\n')).toThrow();
  expect(() => parseOmiChatStream('done: broken\n\n')).toThrow();
});

test('old chat history keeps GET day_summary type instead of dropping it as a normal turn', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'summary-1',
        sender: 'ai',
        text: 'Yesterday you captured two meetings.',
        created_at: '2026-09-07T01:02:03Z',
        type: 'day_summary',
      },
      {
        id: 'text-1',
        sender: 'human',
        text: 'hello',
        created_at: '2026-09-07T01:02:04Z',
        type: 'plugin_event',
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'summary-1')).toEqual(
    expect.objectContaining({id: 'summary-1', type: 'day_summary'}),
  );
  expect(page.messages.find(row => row.id === 'text-1')?.type).toBeUndefined();
});

test('old chat history keeps GET memory citations and omits empty titles', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'cited-1',
        sender: 'ai',
        text: 'I found that meeting.',
        created_at: '2026-09-07T01:02:03Z',
        memories: [
          {
            id: 'conv-1',
            created_at: '2026-09-06T00:00:00Z',
            structured: {title: 'Morning standup', emoji: '🚀'},
          },
          {
            id: 'conv-2',
            created_at: '2026-09-06T00:00:00Z',
            structured: {title: 'Notes', emoji: ''},
          },
          {
            id: 'conv-3',
            created_at: '2026-09-06T00:00:00Z',
            structured: {title: '\u0085', emoji: '🧠'},
          },
        ],
      },
    ]),
    0,
  );
  expect(page.messages[0].memories).toEqual([
    {title: 'Morning standup', emoji: '🚀'},
    {title: 'Notes'},
    {title: '\u0085', emoji: '🧠'},
  ]);
});

test('old chat history names GET evidence and omits conversation refs already cited', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'evidence-1',
        sender: 'ai',
        text: 'On that screen.',
        created_at: '2026-09-07T01:02:03Z',
        memories: [
          {
            id: 'conv-1',
            created_at: '2026-09-06T00:00:00Z',
            structured: {title: 'Morning standup', emoji: '🚀'},
          },
        ],
        evidence: {
          schema_version: 1,
          references: [
            {
              id: 'screen-1',
              kind: 'screen',
              state: 'available',
              title: 'Calendar',
              summary: 'Tuesday agenda',
            },
            {
              id: 'conv-ref',
              kind: 'conversation_summary',
              state: 'available',
              title: 'Morning standup',
            },
          ],
        },
      },
      {
        id: 'evidence-2',
        sender: 'ai',
        text: 'Fallback labels.',
        created_at: '2026-09-07T01:02:04Z',
        evidence: [
          {id: 'key-1', kind: 'keyframe', state: 'offline'},
          {id: 'bad', kind: 'mystery', state: 'nope'},
        ],
      },
      {
        id: 'evidence-3',
        sender: 'ai',
        text: 'Broken envelope stays text.',
        created_at: '2026-09-07T01:02:05Z',
        evidence: 'not-an-object',
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'evidence-1')?.evidence).toEqual([
    {title: 'Calendar', detail: 'Tuesday agenda'},
  ]);
  expect(page.messages.find(row => row.id === 'evidence-2')?.evidence).toEqual([
    {title: 'Screen keyframe', detail: 'Unavailable offline'},
    {title: 'Evidence', detail: 'Unavailable'},
  ]);
  expect(
    page.messages.find(row => row.id === 'evidence-3')?.evidence,
  ).toBeUndefined();
  expect(page.messages.find(row => row.id === 'evidence-3')?.text).toBe(
    'Broken envelope stays text.',
  );
});

test('old chat history rejects malformed GET memories', () => {
  expect(() =>
    parseOmiHistory(
      JSON.stringify([
        {
          id: 'cited-1',
          sender: 'ai',
          text: 'I found that meeting.',
          created_at: '2026-09-07T01:02:03Z',
          memories: [{structured: {title: 'Morning standup'}}],
        },
      ]),
      0,
    ),
  ).toThrow();
});

test('old chat history keeps GET files when files_id is present', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'file-1',
        sender: 'human',
        text: 'Here is the note.',
        created_at: '2026-09-07T01:02:03Z',
        files_id: ['att-notes'],
        files: [
          {
            id: 'att-notes',
            name: 'notes.txt',
            mime_type: 'text/plain',
            openai_file_id: 'file-abc',
            created_at: '2026-09-07T01:00:00Z',
          },
        ],
      },
      {
        id: 'file-hidden',
        sender: 'ai',
        text: 'No ids.',
        created_at: '2026-09-07T01:02:04Z',
        files: [
          {
            id: 'att-hidden',
            name: 'hidden.txt',
            mime_type: 'text/plain',
            openai_file_id: 'file-hidden',
            created_at: '2026-09-07T01:00:00Z',
          },
        ],
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'file-1')?.attachments).toEqual([
    {
      id: 'att-notes',
      displayName: 'notes.txt',
      mediaType: 'text/plain',
    },
  ]);
  expect(
    page.messages.find(row => row.id === 'file-hidden')?.attachments,
  ).toBeUndefined();
});

test('old chat history keeps GET files thumbnail and omits empty paths', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'file-thumb',
        sender: 'human',
        text: 'Here is the photo.',
        created_at: '2026-09-07T01:02:03Z',
        files_id: ['att-photo'],
        files: [
          {
            id: 'att-photo',
            name: 'photo.png',
            mime_type: 'image/png',
            openai_file_id: 'file-photo',
            created_at: '2026-09-07T01:00:00Z',
            thumbnail: 'https://cdn.example/photo.png',
          },
        ],
      },
      {
        id: 'file-empty-thumb',
        sender: 'human',
        text: 'No thumb.',
        created_at: '2026-09-07T01:02:04Z',
        files_id: ['att-empty'],
        files: [
          {
            id: 'att-empty',
            name: 'empty.png',
            mime_type: 'image/png',
            openai_file_id: 'file-empty',
            created_at: '2026-09-07T01:00:00Z',
            thumbnail: ' \t\n',
          },
        ],
      },
    ]),
    0,
  );
  expect(
    page.messages.find(row => row.id === 'file-thumb')?.attachments,
  ).toEqual([
    {
      id: 'att-photo',
      displayName: 'photo.png',
      mediaType: 'image/png',
      thumbnail: 'https://cdn.example/photo.png',
    },
  ]);
  expect(
    page.messages.find(row => row.id === 'file-empty-thumb')?.attachments,
  ).toEqual([
    {
      id: 'att-empty',
      displayName: 'empty.png',
      mediaType: 'image/png',
    },
  ]);
});

test('old chat history rejects malformed GET files thumbnail', () => {
  expect(() =>
    parseOmiHistory(
      JSON.stringify([
        {
          id: 'bad-thumb',
          sender: 'ai',
          text: 'broken',
          created_at: '2026-09-07T01:02:03Z',
          files_id: ['att-notes'],
          files: [
            {
              id: 'att-notes',
              name: 'notes.txt',
              mime_type: 'text/plain',
              openai_file_id: 'file-abc',
              created_at: '2026-09-07T01:00:00Z',
              thumbnail: 1,
            },
          ],
        },
      ]),
      0,
    ),
  ).toThrow('Omi chat files are malformed');
});

test('old chat history keeps GET chart_data points and omits empty charts', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'chart-1',
        sender: 'ai',
        text: 'Here is the trend.',
        created_at: '2026-09-07T01:02:03Z',
        chart_data: {
          chart_type: 'bar',
          title: 'Talk time',
          datasets: [
            {
              label: 'Minutes',
              data_points: [
                {label: 'Mon', value: 12},
                {label: 'Tue', value: 15},
              ],
            },
          ],
        },
      },
      {
        id: 'chart-empty',
        sender: 'ai',
        text: 'No chart.',
        created_at: '2026-09-07T01:02:04Z',
        chart_data: {
          chart_type: 'line',
          title: 'Empty',
          datasets: [{label: 'Minutes', data_points: []}],
        },
      },
      {
        id: 'chart-untyped',
        sender: 'ai',
        text: 'Not a chart.',
        created_at: '2026-09-07T01:02:05Z',
        chart_data: {title: 'Nope'},
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'chart-1')?.chart).toEqual({
    title: 'Talk time',
    points: [
      {label: 'Mon', value: 12},
      {label: 'Tue', value: 15},
    ],
  });
  expect(
    page.messages.find(row => row.id === 'chart-empty')?.chart,
  ).toBeUndefined();
  expect(
    page.messages.find(row => row.id === 'chart-untyped')?.chart,
  ).toBeUndefined();
});

test('old chat history rejects malformed GET chart_data', () => {
  expect(() =>
    parseOmiHistory(
      JSON.stringify([
        {
          id: 'bad-chart',
          sender: 'ai',
          text: 'broken',
          created_at: '2026-09-07T01:02:03Z',
          chart_data: 'not-an-object',
        },
      ]),
      0,
    ),
  ).toThrow();
});

test('old chat history rejects malformed GET files', () => {
  expect(() =>
    parseOmiHistory(
      JSON.stringify([
        {
          id: 'bad-file',
          sender: 'ai',
          text: 'broken',
          created_at: '2026-09-07T01:02:03Z',
          files_id: ['att-notes'],
          files: [{id: 'att-notes', name: 1, mime_type: 'text/plain'}],
        },
      ]),
      0,
    ),
  ).toThrow('Omi chat files are malformed');
});

test('old chat history keeps GET plugin_id over app_id and omits empty ids', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'plugin',
        sender: 'ai',
        text: 'Saved.',
        created_at: '2026-09-07T01:02:03Z',
        plugin_id: 'notes',
        app_id: 'ignored',
      },
      {
        id: 'app-only',
        sender: 'ai',
        text: 'Logged.',
        created_at: '2026-09-07T01:02:04Z',
        app_id: 'logger',
      },
      {
        id: 'empty',
        sender: 'ai',
        text: 'Plain.',
        created_at: '2026-09-07T01:02:05Z',
        plugin_id: ' \t',
        app_id: '',
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'plugin')).toEqual(
    expect.objectContaining({appId: 'notes'}),
  );
  expect(page.messages.find(row => row.id === 'app-only')).toEqual(
    expect.objectContaining({appId: 'logger'}),
  );
  expect(page.messages.find(row => row.id === 'empty')).not.toHaveProperty(
    'appId',
  );
});

test('old chat history names GET content_blocks without inventing writes', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'blocks-1',
        sender: 'ai',
        text: 'Here is what I found.',
        created_at: '2026-09-07T01:02:03Z',
        content_blocks: [
          {
            type: 'discoveryCard',
            id: 'd1',
            title: 'Quiet mornings',
            summary: 'You like a slow start.',
            full_text: 'Longer body stays collapsed.',
          },
          {
            type: 'memory_link',
            id: 'm1',
            memory_id: 'mem-1',
            summary: 'Prefers concise notes',
          },
          {
            type: 'goalLink',
            id: 'g1',
            goalId: 'goal-1',
            summary: 'Ship the release notes',
          },
          {
            type: 'conversation_link',
            id: 'c1',
            conversation_id: 'conv-1',
            summary: 'Standup recap',
            recommended_action_items: [{description: 'Send the agenda'}],
          },
          {
            type: 'question_card',
            id: 'q1',
            question_id: 'q-1',
            text: 'Schedule the follow-up?',
            subject: {kind: 'task', id: 'task-1'},
            options: [
              {option_id: 'yes', label: 'Yes, schedule it'},
              {option_id: 'no', label: 'Not now'},
            ],
          },
          {
            type: 'task_card',
            id: 't1',
            task_id: 'task-1',
          },
          {
            type: 'agent_spawn',
            id: 'a1',
            session_id: 'sess-1',
            run_id: 'run-1',
            title: 'Draft recap',
            objective: 'Summarize standup',
          },
          {
            type: 'agent_completion',
            id: 'a2',
            status: 'timed_out',
            title: 'Draft recap',
            output: 'Stopped waiting.',
          },
        ],
      },
      {
        id: 'blocks-answered',
        sender: 'ai',
        text: 'Noted.',
        created_at: '2026-09-07T01:02:04Z',
        content_blocks: [
          {
            type: 'questionCard',
            id: 'q2',
            questionId: 'q-2',
            text: 'Keep this goal?',
            subject: {kind: 'goal', id: 'goal-2'},
            selectedOptionId: 'keep',
            options: [
              {optionId: 'keep', label: 'Keep it'},
              {optionId: 'drop', label: 'Drop it'},
            ],
          },
        ],
      },
      {
        id: 'blocks-malformed',
        sender: 'ai',
        text: 'Plain answer stays.',
        created_at: '2026-09-07T01:02:05Z',
        content_blocks: 'not-an-array',
      },
      {
        id: 'blocks-metadata',
        sender: 'ai',
        text: 'From metadata.',
        created_at: '2026-09-07T01:02:06Z',
        metadata: JSON.stringify({
          content_blocks: [
            {
              type: 'capture_link',
              id: 'cap-1',
              conversation_id: 'conv-2',
              summary: 'Kitchen capture',
            },
          ],
        }),
      },
    ]),
    0,
  );
  expect(
    page.messages.find(row => row.id === 'blocks-1')?.contentBlocks,
  ).toEqual([
    {
      eyebrow: 'Discovery',
      title: 'Quiet mornings',
      detail: 'You like a slow start.',
    },
    {eyebrow: 'Memory', title: 'Prefers concise notes'},
    {eyebrow: 'Goal', title: 'Ship the release notes'},
    {eyebrow: 'Conversation', title: 'Standup recap'},
    {eyebrow: 'Recommended next steps', title: 'Send the agenda'},
    {
      eyebrow: 'Question',
      title: 'Schedule the follow-up?',
      detail: 'Yes, schedule it · Not now',
    },
    {eyebrow: 'Task', taskId: 'task-1'},
    {
      eyebrow: 'Processing',
      title: 'Draft recap',
      detail: 'Summarize standup',
    },
    {
      eyebrow: 'Timed out',
      title: 'Draft recap',
      detail: 'Stopped waiting.',
    },
  ]);
  expect(
    page.messages.find(row => row.id === 'blocks-answered')?.contentBlocks,
  ).toEqual([
    {eyebrow: 'Question', title: 'Keep this goal?', detail: 'Keep it'},
  ]);
  expect(
    page.messages.find(row => row.id === 'blocks-malformed')?.contentBlocks,
  ).toBeUndefined();
  expect(page.messages.find(row => row.id === 'blocks-malformed')?.text).toBe(
    'Plain answer stays.',
  );
  expect(
    page.messages.find(row => row.id === 'blocks-metadata')?.contentBlocks,
  ).toEqual([{eyebrow: 'Conversation', title: 'Kitchen capture'}]);
});

test('old chat history names empty-text GET tool thinking and citation fallbacks', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'fallback-1',
        sender: 'ai',
        text: '',
        created_at: '2026-09-07T01:02:03Z',
        content_blocks: [
          {
            type: 'tool_call',
            id: 'tool-1',
            name: 'Search',
            output: 'Found two notes',
            input_summary: 'standup recap',
          },
          {
            type: 'thinking',
            id: 'think-1',
            text: 'Need the agenda first',
          },
          {
            type: 'citation',
            id: 'cite-1',
            title: 'Standup notes',
            preview: 'Ship the recap today',
          },
          {
            type: 'discoveryCard',
            id: 'd1',
            title: 'Quiet mornings',
            summary: 'You like a slow start.',
          },
          {
            type: 'taskCard',
            id: 't1',
            taskId: 'task-1',
          },
        ],
      },
      {
        id: 'fallback-kept',
        sender: 'ai',
        text: 'Here is what I found.',
        created_at: '2026-09-07T01:02:04Z',
        content_blocks: [
          {
            type: 'toolCall',
            id: 'tool-2',
            name: 'Search',
            output: 'Should stay omitted',
          },
        ],
      },
      {
        id: 'fallback-empty-tool',
        sender: 'ai',
        text: ' \t',
        created_at: '2026-09-07T01:02:05Z',
        content_blocks: [{type: 'thinking', id: 'think-empty'}],
      },
    ]),
    0,
  );
  expect(page.messages.find(row => row.id === 'fallback-1')?.text).toBe(
    'Tool - Search - Found two notes - standup recap\nThinking - Need the agenda first\nSource - Standup notes - Ship the recap today',
  );
  expect(
    page.messages.find(row => row.id === 'fallback-1')?.contentBlocks,
  ).toEqual([
    {
      eyebrow: 'Discovery',
      title: 'Quiet mornings',
      detail: 'You like a slow start.',
    },
    {eyebrow: 'Task', taskId: 'task-1'},
  ]);
  expect(page.messages.find(row => row.id === 'fallback-kept')?.text).toBe(
    'Here is what I found.',
  );
  expect(
    page.messages.find(row => row.id === 'fallback-kept')?.contentBlocks,
  ).toBeUndefined();
  expect(
    page.messages.find(row => row.id === 'fallback-empty-tool')?.text,
  ).toBe('Thinking');
  const copy = JSON.stringify(page.messages);
  expect(copy).not.toContain('Should stay omitted');
  expect(
    page.messages.find(row => row.id === 'fallback-1')?.text,
  ).not.toContain('task-1');
  expect(copy).not.toContain('Show more');
});

test('old chat history names GET memory review cards without inventing writes', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'review-1',
        sender: 'ai',
        text: 'Here is what I learned.',
        created_at: '2026-09-07T01:02:03Z',
        content_blocks: [
          {
            type: 'memory_review_card',
            id: 'learned-1',
            summary_id: 'sum-1',
            date: '2026-09-07',
            items: [
              {
                memory_id: 'mem-work',
                content: 'Prefers morning standups',
                category: 'work',
              },
              {
                memoryId: 'mem-empty',
                content: ' \t',
                category: 'interesting',
              },
              {
                memory_id: 'mem-core',
                content: 'Lives in San Francisco',
                category: 'core_memory',
              },
              {
                memory_id: 'mem-plain',
                content: 'Drinks tea',
              },
              {
                memory_id: 'mem-fourth',
                content: 'Should not appear',
                category: 'work',
              },
            ],
          },
        ],
      },
      {
        id: 'review-camel',
        sender: 'ai',
        text: 'Also learned.',
        created_at: '2026-09-07T01:02:04Z',
        content_blocks: [
          {
            type: 'memoryReviewCard',
            id: 'learned-2',
            items: [
              {
                memoryId: 'mem-2',
                content: 'Uses a standing desk',
                category: 'interesting',
              },
            ],
          },
        ],
      },
      {
        id: 'review-empty',
        sender: 'ai',
        text: 'No learned rows.',
        created_at: '2026-09-07T01:02:05Z',
        content_blocks: [
          {
            type: 'memory_review_card',
            id: 'learned-empty',
            items: [{memory_id: 'mem-blank', content: '  '}],
          },
        ],
      },
    ]),
    0,
  );
  expect(
    page.messages.find(row => row.id === 'review-1')?.contentBlocks,
  ).toEqual([
    {
      eyebrow: 'Things I learned today',
      title: 'Prefers morning standups',
      detail: 'Work',
    },
    {
      eyebrow: 'Things I learned today',
      title: 'Lives in San Francisco',
      detail: 'Core memory',
    },
    {eyebrow: 'Things I learned today', title: 'Drinks tea'},
  ]);
  expect(
    page.messages.find(row => row.id === 'review-camel')?.contentBlocks,
  ).toEqual([
    {
      eyebrow: 'Things I learned today',
      title: 'Uses a standing desk',
      detail: 'Interesting',
    },
  ]);
  expect(
    page.messages.find(row => row.id === 'review-empty')?.contentBlocks,
  ).toBeUndefined();
  expect(page.messages.find(row => row.id === 'review-empty')?.text).toBe(
    'No learned rows.',
  );
  const copy = JSON.stringify(page.messages);
  expect(copy).not.toContain('✓ Right');
  expect(copy).not.toContain('✗ Wrong');
  expect(copy).not.toContain("'Fix'");
  expect(copy).not.toContain('mem-work');
  expect(copy).not.toContain('Should not appear');
});

test('old chat history names GET followUp text and omits empty or send chips', () => {
  const page = parseOmiHistory(
    JSON.stringify([
      {
        id: 'follow-1',
        sender: 'ai',
        text: 'Here is what I found.',
        created_at: '2026-09-07T01:02:03Z',
        content_blocks: [
          {
            type: 'followUp',
            text: 'Want me to draft the recap next?',
          },
        ],
      },
      {
        id: 'follow-snake',
        sender: 'ai',
        text: 'Also this.',
        created_at: '2026-09-07T01:02:04Z',
        content_blocks: [
          {
            type: 'follow_up',
            id: 'fu-2',
            text: '  Should I schedule standup?  ',
          },
        ],
      },
      {
        id: 'follow-empty',
        sender: 'ai',
        text: 'No invite.',
        created_at: '2026-09-07T01:02:05Z',
        content_blocks: [{type: 'followUp', text: ' \t'}],
      },
      {
        id: 'follow-fallback',
        sender: 'ai',
        text: '',
        created_at: '2026-09-07T01:02:06Z',
        content_blocks: [
          {
            type: 'follow_up',
            text: 'Want me to draft the recap next?',
          },
        ],
      },
    ]),
    0,
  );
  expect(
    page.messages.find(row => row.id === 'follow-1')?.contentBlocks,
  ).toEqual([{eyebrow: 'Want me to draft the recap next?'}]);
  expect(
    page.messages.find(row => row.id === 'follow-snake')?.contentBlocks,
  ).toEqual([{eyebrow: 'Should I schedule standup?'}]);
  expect(
    page.messages.find(row => row.id === 'follow-empty')?.contentBlocks,
  ).toBeUndefined();
  expect(page.messages.find(row => row.id === 'follow-empty')?.text).toBe(
    'No invite.',
  );
  const fallback = page.messages.find(row => row.id === 'follow-fallback');
  expect(fallback?.text).toBe('');
  expect(fallback?.contentBlocks).toEqual([
    {eyebrow: 'Want me to draft the recap next?'},
  ]);
  const serialized = JSON.stringify(page.messages);
  expect(serialized).not.toContain('preparedAnswer');
  expect(serialized).not.toContain('onSend');
});
