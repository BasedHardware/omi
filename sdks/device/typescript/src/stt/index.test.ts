import { describe, expect, test } from 'bun:test';
import { createDeepgramTranscriber, deepgramWsUrl, deepgramWsUrlWithToken } from './index.ts';

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

describe('deepgramWsUrlWithToken', () => {
  test('includes token query param (deprecated)', () => {
    const url = deepgramWsUrlWithToken('test-key-123', 16000);
    expect(url).toInclude('token=test-key-123');
  });

  test('encodes special characters in token', () => {
    const url = deepgramWsUrlWithToken('key with spaces & stuff=', 16000);
    expect(url).toInclude('token=key%20with%20spaces%20%26%20stuff%3D');
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

  test('connects with apiKey fallback (deprecated)', () => {
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
      apiKey: 'dg-123',
      onTranscript: () => {},
      WebSocketImpl: FakeWebSocket as any,
    });

    expect(openedUrl).toInclude('token=dg-123');
    expect(openedUrl).toInclude('sample_rate=16000');
  });
});
