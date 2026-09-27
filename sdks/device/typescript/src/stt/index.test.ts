import { describe, expect, test } from 'bun:test';
import {
  createDeepgramTranscriber,
  createParakeetTranscriber,
  createTranscriber,
  createWhisperTranscriber,
  deepgramWsUrl,
  parakeetWsUrl,
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

  test('sends CloseStream before closing the socket', async () => {
    const sent: unknown[] = [];
    const events: Array<'send' | 'close'> = [];
    let closeCount = 0;
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(data: unknown) {
        events.push('send');
        sent.push(data);
      }
      close() {
        events.push('close');
        closeCount += 1;
        this.readyState = 3;
      }
    }

    const transcriber = createDeepgramTranscriber({
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
      drainTimeoutMs: 50,
    });
    transcriber.stop();
    expect(events).toEqual(['send']);
    await new Promise((resolve) => setTimeout(resolve, 70));

    expect(events).toEqual(['send', 'close']);
    expect(sent).toEqual([JSON.stringify({ type: 'CloseStream' })]);
    expect(closeCount).toBe(1);
  });

  test('closes after CloseStream when the provider closes the socket', async () => {
    const events: Array<'send' | 'close'> = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(data: unknown) {
        events.push('send');
        queueMicrotask(() => {
          this.readyState = 3;
          this.onclose?.({} as Event);
        });
      }
      close() {
        events.push('close');
        this.readyState = 3;
      }
    }

    const transcriber = createDeepgramTranscriber({
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
      drainTimeoutMs: 5000,
    });
    transcriber.stop();
    await Promise.resolve();
    await Promise.resolve();

    expect(events).toEqual(['send', 'close']);
  });

  test('drains a trailing transcript after CloseStream', async () => {
    const transcripts: string[] = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(_data: unknown) {}
      close() {
        this.readyState = 3;
      }
    }

    const socket = new FakeWebSocket('');
    const transcriber = createDeepgramTranscriber({
      onTranscript: (text) => transcripts.push(text),
      createWebSocket: () => socket as any,
      drainTimeoutMs: 50,
    });
    transcriber.stop();
    socket.onmessage?.({
      data: JSON.stringify({
        channel: { alternatives: [{ transcript: 'late ts' }] },
      }),
    } as MessageEvent);
    await new Promise((resolve) => setTimeout(resolve, 70));

    expect(transcripts).toEqual(['late ts']);
  });

  test('closes the socket when CloseStream send fails', () => {
    const events: Array<'send' | 'close'> = [];
    let closeCount = 0;
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {}
      send(_data: unknown) {
        events.push('send');
        throw new Error('synthetic send failure');
      }
      close() {
        events.push('close');
        closeCount += 1;
        this.readyState = 3;
      }
    }

    const transcriber = createDeepgramTranscriber({
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
    });
    transcriber.stop();

    expect(events).toEqual(['send', 'close']);
    expect(closeCount).toBe(1);
  });

  test('does not send CloseStream when the socket is already closed', () => {
    const sent: unknown[] = [];
    const events: Array<'send' | 'close'> = [];
    let closeCount = 0;
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 3;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {}
      send(data: unknown) {
        events.push('send');
        sent.push(data);
      }
      close() {
        events.push('close');
        closeCount += 1;
      }
    }

    const transcriber = createDeepgramTranscriber({
      onTranscript: () => {},
      createWebSocket: (url: string) => new FakeWebSocket(url) as any,
    });
    transcriber.stop();

    expect(events).toEqual(['close']);
    expect(sent).toEqual([]);
    expect(closeCount).toBe(1);
  });
});

describe('createWhisperTranscriber', () => {
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

describe('parakeetWsUrl', () => {
  test('converts https to wss and appends streaming endpoint', () => {
    const url = parakeetWsUrl('https://parakeet.example');
    expect(url).toBe('wss://parakeet.example/v3/stream?sample_rate=16000');
  });

  test('converts http to ws', () => {
    const url = parakeetWsUrl('http://parakeet.example:8080');
    expect(url).toBe('ws://parakeet.example:8080/v3/stream?sample_rate=16000');
  });

  test('preserves existing path and query parameters', () => {
    const url = parakeetWsUrl('https://parakeet.example/gateway?region=eu');
    expect(url).toBe('wss://parakeet.example/gateway/v3/stream?region=eu&sample_rate=16000');
  });

  test('strips trailing slashes from path before appending stream endpoint', () => {
    const url = parakeetWsUrl('https://parakeet.example/gateway/');
    expect(url).toBe('wss://parakeet.example/gateway/v3/stream?sample_rate=16000');
  });

  test('removes hash fragments', () => {
    const url = parakeetWsUrl('https://parakeet.example/gateway?region=eu#debug');
    expect(url).toBe('wss://parakeet.example/gateway/v3/stream?region=eu&sample_rate=16000');
  });

  test('supports custom sample rate', () => {
    const url = parakeetWsUrl('https://parakeet.example', 8000);
    expect(url).toBe('wss://parakeet.example/v3/stream?sample_rate=8000');
  });

  test('rejects unsupported protocols', () => {
    expect(() => parakeetWsUrl('ftp://parakeet.example')).toThrow(TypeError);
  });
});

describe('createParakeetTranscriber', () => {
  test('connects to parakeetWsUrl with query params preserved', () => {
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

    createParakeetTranscriber({
      apiUrl: 'https://parakeet.example/gateway?region=eu',
      sampleRate: 16000,
      onTranscript: () => {},
      WebSocketImpl: FakeWebSocket as any,
    });

    expect(openedUrl).toBe('wss://parakeet.example/gateway/v3/stream?region=eu&sample_rate=16000');
  });

  test('sends finalize before closing the socket', async () => {
    const sent: unknown[] = [];
    const events: Array<'send' | 'close'> = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(data: unknown) {
        events.push('send');
        sent.push(data);
      }
      close() {
        events.push('close');
        this.readyState = 3;
      }
    }

    const transcriber = createParakeetTranscriber({
      apiUrl: 'https://parakeet.example',
      onTranscript: () => {},
      WebSocketImpl: FakeWebSocket as any,
      drainTimeoutMs: 50,
    });
    transcriber.stop();
    expect(events).toEqual(['send']);
    await new Promise((resolve) => setTimeout(resolve, 70));

    expect(events).toEqual(['send', 'close']);
    expect(sent).toEqual(['finalize']);
  });

  test('drains a trailing transcript after finalize', async () => {
    const transcripts: string[] = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(_data: unknown) {}
      close() {
        this.readyState = 3;
      }
    }

    const socketHolder: { socket?: FakeWebSocket } = {};
    class CapturingSocket extends FakeWebSocket {
      constructor(url: string) {
        super(url);
        socketHolder.socket = this;
      }
    }

    const transcriber = createParakeetTranscriber({
      apiUrl: 'https://parakeet.example',
      onTranscript: (text) => transcripts.push(text),
      WebSocketImpl: CapturingSocket as any,
      drainTimeoutMs: 50,
    });
    transcriber.stop();
    expect(socketHolder.socket?.readyState).toBe(1);
    socketHolder.socket?.onmessage?.({
      data: JSON.stringify({ text: 'late para' }),
    } as MessageEvent);
    await new Promise((resolve) => setTimeout(resolve, 70));

    expect(transcripts).toEqual(['late para']);
  });

  test('rejects PCM and a second finalize while the socket is draining', () => {
    const sent: unknown[] = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: Event) => void) | null = null;
      constructor(_url: string) {}
      send(data: unknown) {
        sent.push(data);
      }
      close() {
        this.readyState = 3;
      }
    }

    const socketHolder: { socket?: FakeWebSocket } = {};
    class CapturingSocket extends FakeWebSocket {
      constructor(url: string) {
        super(url);
        socketHolder.socket = this;
      }
    }

    const transcriber = createParakeetTranscriber({
      apiUrl: 'https://parakeet.example',
      onTranscript: () => {},
      WebSocketImpl: CapturingSocket as any,
      drainTimeoutMs: 5000,
    });
    socketHolder.socket?.onmessage?.({
      data: JSON.stringify({ type: 'ready' }),
    } as MessageEvent);
    transcriber.appendPcm(new Uint8Array([1, 2]));
    transcriber.stop();
    transcriber.appendPcm(new Uint8Array([3, 4]));
    transcriber.stop();

    expect(sent).toEqual([new Uint8Array([1, 2]), 'finalize']);
    expect(socketHolder.socket?.readyState).toBe(1);
  });

  test('closes the socket when finalize send fails', () => {
    const events: Array<'send' | 'close'> = [];
    class FakeWebSocket {
      binaryType: string = 'blob';
      readyState = 1;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {}
      send(_data: unknown) {
        events.push('send');
        throw new Error('synthetic send failure');
      }
      close() {
        events.push('close');
        this.readyState = 3;
      }
    }

    const transcriber = createParakeetTranscriber({
      apiUrl: 'https://parakeet.example',
      onTranscript: () => {},
      WebSocketImpl: FakeWebSocket as any,
    });
    transcriber.stop();

    expect(events).toEqual(['send', 'close']);
  });
});
