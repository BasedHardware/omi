import { describe, expect, test } from 'bun:test';
import {
  createDeepgramTranscriber,
  createTranscriber,
  createWhisperTranscriber,
  deepgramWsUrl,
} from './index.ts';

describe('deepgramWsUrl', () => {
  test('returns base URL without token', () => {
    const url = deepgramWsUrl(16000);
    expect(url).not.toInclude('token=');
    expect(url).toStartWith('wss://api.deepgram.com/v1/listen?');
    expect(url).toInclude('sample_rate=16000');
  });

  test('uses custom sample rate', () => {
    const url = deepgramWsUrl(8000);
    expect(url).toInclude('sample_rate=8000');
  });
});

describe('createDeepgramTranscriber', () => {
  test('connects via createWebSocket factory (token-free URL)', () => {
    let openedUrl: string | undefined;
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(url: string) {
        openedUrl = url;
      }
      send(_data: any) {}
      close() {}
    }

    createDeepgramTranscriber({
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
    });

    expect(openedUrl).not.toInclude('token=');
    expect(openedUrl).toInclude('sample_rate=16000');
  });

  test('rejects apiKey-only construction so a credential cannot enter the URL', () => {
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {}
      send(_data: any) {}
      close() {}
    }

    expect(() =>
      (createDeepgramTranscriber as (opts: any) => unknown)({
        apiKey: 'dg-123',
        onTranscript: () => {},
        WebSocketImpl: FakeWebSocket,
      }),
    ).toThrow('Deepgram requires createWebSocket');
  });

  test('createTranscriber accepts an authenticated WebSocket factory without apiKey', () => {
    let openedUrl: string | undefined;
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(url: string) {
        openedUrl = url;
      }
      send(_data: any) {}
      close() {}
    }

    createTranscriber('deepgram', {
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
    });

    expect(openedUrl).not.toInclude('token=');
  });
});

describe('createWhisperTranscriber', () => {
  test('delivers an in-flight full batch after stop and ignores later audio', async () => {
    const transcripts: string[] = [];
    const batches: Uint8Array[] = [];
    let finish!: (text: string) => void;
    const pending = new Promise<string>((resolve) => { finish = resolve; });
    const transcriber = createWhisperTranscriber({
      runner: (pcm) => { batches.push(pcm); return pending; },
      onTranscript: (text) => transcripts.push(text),
      batchSeconds: 1,
    });

    transcriber.appendPcm(new Uint8Array(32000).fill(7));
    transcriber.stop();
    transcriber.stop();
    transcriber.appendPcm(new Uint8Array(32000).fill(9));
    finish('accepted audio');
    await pending;

    expect(batches).toHaveLength(1);
    expect(batches[0]).toEqual(new Uint8Array(32000).fill(7));
    expect(transcripts).toEqual(['accepted audio']);
  });

  test('delivers both an in-flight batch and the buffered tail on stop', async () => {
    const transcripts: string[] = [];
    const completions: ((text: string) => void)[] = [];
    const pending: Promise<string>[] = [];
    const transcriber = createWhisperTranscriber({
      runner: () => {
        const result = new Promise<string>((resolve) => completions.push(resolve));
        pending.push(result);
        return result;
      },
      onTranscript: (text) => transcripts.push(text),
      batchSeconds: 1,
    });

    transcriber.appendPcm(new Uint8Array(32000));
    transcriber.appendPcm(new Uint8Array(2));
    transcriber.stop();
    completions[0]('full batch');
    await pending[0];
    completions[1]('tail');
    await pending[1];

    expect(transcripts).toEqual(['full batch', 'tail']);
  });

  test('delivers buffered audio transcript when stopped before a batch fills', async () => {
    const transcripts: string[] = [];
    const transcriber = createWhisperTranscriber({
      runner: () => 'final transcript',
      onTranscript: (text) => transcripts.push(text),
      batchSeconds: 5,
    });

    transcriber.appendPcm(new Uint8Array([1, 2, 3]));
    transcriber.stop();
    await Promise.resolve();
    await Promise.resolve();

    expect(transcripts).toEqual(['final transcript']);
  });
});
