import {decodeBase64, encodeBase64} from './base64';
import {parseOmiChatStream} from './legacyOmiChat';
import {decodeJournalPacket} from './recordingJournalClient';
import {appendDeviceSessionAudio} from './deviceSessionClient';
import type {OmiBackend, NativeHttpRequest} from './omiNativeTypes';

const atobDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'atob');
const btoaDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'btoa');
beforeAll(() => {
  Reflect.deleteProperty(globalThis, 'atob');
  Reflect.deleteProperty(globalThis, 'btoa');
});
afterAll(() => {
  if (atobDescriptor) Object.defineProperty(globalThis, 'atob', atobDescriptor);
  if (btoaDescriptor) Object.defineProperty(globalThis, 'btoa', btoaDescriptor);
});

test('canonical binary codec works without browser globals', () => {
  expect(globalThis.atob).toBeUndefined();
  expect(globalThis.btoa).toBeUndefined();
  const bytes = Uint8Array.from([0, 255, 128, 17]);
  expect(encodeBase64(bytes)).toBe('AP+AEQ==');
  expect(decodeBase64('AP+AEQ==')).toEqual(bytes);
  expect(decodeJournalPacket('AP+AEQ==')).toEqual(bytes);
});

test.each([
  'A',
  'AAA',
  'A===',
  'AA=A',
  'AA==extra',
  'AA-_',
  'AA==\n',
  'AB==',
  'AAB=',
])('rejects noncanonical base64 %s', value => {
  expect(() => decodeBase64(value)).toThrow();
});

test('old server done frame displays Unicode under the native runtime global shape', () => {
  const terminal = Buffer.from(
    JSON.stringify({
      id: 'server-message',
      sender: 'ai',
      text: 'Hello 世界 👋',
      created_at: '2026-09-09T00:00:00Z',
    }),
  ).toString('base64');
  expect(parseOmiChatStream(`done: ${terminal}\n\n`).text).toBe(
    'Hello 世界 👋',
  );
  expect(() => parseOmiChatStream('done: /w==\n\n')).toThrow();
});

test('actual audio append uses the same native-safe encoder', async () => {
  const id = '11111111-2222-4333-8444-555555555555';
  const request = jest.fn(async (_request: NativeHttpRequest) => ({
    id: 'ack',
    status: 200,
    body: JSON.stringify({
      session: {
        id,
        deviceId: 'omi',
        deviceName: null,
        codec: 21,
        state: 'open',
        byteCount: 4,
        chunkCount: 1,
        startedAt: 1,
        endedAt: null,
      },
    }),
  }));
  await appendDeviceSessionAudio(
    {request} as unknown as OmiBackend,
    id,
    [Uint8Array.from([0, 255, 128, 17])],
    0,
  );
  expect(JSON.parse(request.mock.calls[0]?.[0]?.body ?? '{}')).toEqual({
    chunks: [{chunkIndex: 0, bytesBase64: 'AP+AEQ=='}],
  });
});
