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
