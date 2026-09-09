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
