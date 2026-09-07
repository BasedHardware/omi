import {
  createRecordingJournal,
  recordingJournalBackend,
  restoreRecording,
} from '../src/recordingJournalClient';
import type {OmiBackend, RecordingJournal} from '../src/omiNativeTypes';

const captureId = '11111111-2222-4333-8444-555555555555';
const sessionId = '99999999-2222-4333-8444-555555555555';
const journal = (entries: unknown[][] = []): RecordingJournal => ({
  handle: captureId,
  captureId,
  sessionId,
  deviceId: 'omi-1',
  deviceName: null,
  codec: 21,
  entries: entries.map(value => JSON.stringify(value)),
});

test('recovery retains an uploaded packet whose local acknowledgement was lost', () => {
  const saved = journal([['p', 'AAAB'], ['p', 'AAAC'], ['a', 1], ['s']]);
  const restored = restoreRecording(saved);
  expect(restored.acknowledged).toBe(1);
  expect(restored.totalBytes).toBe(6);
  expect(restored.pending).toEqual([new Uint8Array([0, 0, 2])]);
  expect(
    restoreRecording({...saved, entries: saved.entries.slice(0, 2)}).pending,
  ).toHaveLength(2);
});

test('recovery rejects impossible acknowledgement order and packets after stop', () => {
  for (const records of [
    [
      ['p', 'AAAB'],
      ['a', 2],
    ],
    [
      ['p', 'AAAB'],
      ['a', 1],
      ['a', 0],
    ],
    [['p', 'AAAB'], ['s'], ['p', 'AAAC']],
    [['p', 'malformed!']],
  ]) {
    expect(() => restoreRecording(journal(records))).toThrow();
  }
  expect(() =>
    restoreRecording({
      ...journal([
        ['p', 'AAAB'],
        ['a', 1],
      ]),
      sessionId: null,
    }),
  ).toThrow();
});

test('recovery rejects an altered native identity and excessive packet count', () => {
  expect(() => restoreRecording({...journal(), handle: 'different'})).toThrow();
  expect(() =>
    restoreRecording(
      journal(Array.from({length: 65_537}, () => ['p', 'AQ=='])),
    ),
  ).toThrow();
});

test('constrained transport sends the native journal handle without exposing ownership material', async () => {
  const requestRecordingJournal = jest.fn(async () => ({
    id: 'one',
    status: 200,
    body: '{}',
  }));
  const backend: OmiBackend = {
    request: jest.fn(),
    generationEvents: jest.fn(),
    cancelGenerationEvents: jest.fn(),
    createRecordingJournal: jest.fn(async () => ({
      ...journal(),
      sessionId: null,
    })),
    listRecordingJournals: jest.fn(),
    readRecordingJournal: jest.fn(),
    appendRecordingJournal: jest.fn(),
    removeRecordingJournal: jest.fn(),
    requestRecordingJournal,
  };
  const input = {deviceId: 'omi-1', codec: 21};
  const created = await createRecordingJournal(backend, input);
  const request = {
    id: 'one',
    method: 'POST' as const,
    path: '/v1/device-sessions' as const,
    body: JSON.stringify(input),
  };
  await recordingJournalBackend(backend, created.handle).request(request);
  expect(requestRecordingJournal).toHaveBeenCalledWith(captureId, request);
  expect(backend.request).not.toHaveBeenCalled();
  await expect(
    createRecordingJournal(backend, {...input, codec: 20}),
  ).rejects.toThrow('acknowledgement');
});

test('legacy journal capture time remains absent and malformed persisted time is rejected', () => {
  expect(restoreRecording(journal()).journal).not.toHaveProperty(
    'capturedAtMs',
  );
  expect(
    restoreRecording({...journal(), capturedAtMs: 0}).journal.capturedAtMs,
  ).toBe(0);
  for (const value of [null, -1, 0.5, Infinity, 8640000000000001, '1000']) {
    expect(() =>
      restoreRecording({...journal(), capturedAtMs: value as number}),
    ).toThrow('identity is invalid');
  }
});
