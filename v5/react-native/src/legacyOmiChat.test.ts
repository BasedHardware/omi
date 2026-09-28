import {
  IncrementalOmiChatParser,
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

test('old stream parser yields data across split UTF-8 and CRLF frames then reconciles done', () => {
  const terminal = Buffer.from(
    JSON.stringify(message('server-id', 'ai', 'Hello 世界')),
  ).toString('base64');
  const parser = new IncrementalOmiChatParser();
  const world = Buffer.from('世界', 'utf8');
  expect(parser.push('data: Hel')).toEqual([]);
  expect(parser.push('lo ')).toEqual([]);
  expect([
    ...parser.push(world.subarray(0, 2)),
    ...parser.push(world.subarray(2)),
  ]).toEqual([]);
  expect(parser.push('\n\nthink: searching__CRLF__now\r\n\r\n')).toEqual([
    {kind: 'data', text: 'Hello 世界'},
    {kind: 'think', text: 'searching\nnow'},
  ]);
  expect(parser.push(`done: ${terminal.slice(0, 8)}`)).toEqual([]);
  expect(parser.push(`${terminal.slice(8)}\n\n`)).toEqual([
    expect.objectContaining({
      kind: 'done',
      message: expect.objectContaining({id: 'server-id', text: 'Hello 世界'}),
    }),
  ]);
});
