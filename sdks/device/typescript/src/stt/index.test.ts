import { describe, expect, test } from 'bun:test';
import { createDeepgramTranscriber, deepgramWsUrl } from './index.ts';

describe('deepgramWsUrl', () => {
  test('includes token query param', () => {
    const url = deepgramWsUrl('test-key-123', 16000);
    expect(url).toInclude('token=test-key-123');
    expect(url).toStartWith('wss://api.deepgram.com/v1/listen?');
  });

  test('encodes special characters in token', () => {
    const url = deepgramWsUrl('key with spaces & stuff=', 16000);
    expect(url).toInclude('token=key%20with%20spaces%20%26%20stuff%3D');
  });

  test('uses custom sample rate', () => {
    const url = deepgramWsUrl('test-key', 8000);
    expect(url).toInclude('sample_rate=8000');
  });
});

describe('createDeepgramTranscriber', () => {
  test('connects to authenticated Deepgram URL', () => {
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
