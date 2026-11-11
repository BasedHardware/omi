import { beforeEach, describe, expect, it, vi } from 'vitest';

const doubles = vi.hoisted(() => ({
  captureOptions: null as null | {
    onAudioData: (pcm: Int16Array) => void;
    onMicLevel: (level: number) => void;
  },
  start: vi.fn(async () => undefined),
  stop: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
}));

vi.mock('@/lib/audioCapture', () => ({
  createAudioCapture: (options: typeof doubles.captureOptions) => {
    doubles.captureOptions = options;
    return {
      start: doubles.start,
      stop: doubles.stop,
      pause: doubles.pause,
      resume: doubles.resume,
    };
  },
}));

const { GeminiLiveClient, geminiUsageReport } = await import('@/lib/geminiLive');

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.OPEN;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(message: string) {
    this.sent.push(message);
  }

  close() {
    this.onclose?.();
  }

  emit(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  doubles.captureOptions = null;
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

describe('GeminiLiveClient', () => {
  it('uses the native macOS Gemini protocol and commits completed turns', async () => {
    const callbacks = {
      onReady: vi.fn(),
      onLevel: vi.fn(),
      onTranscript: vi.fn(),
      onExchange: vi.fn(),
      onUsage: vi.fn(),
      onError: vi.fn(),
      onClose: vi.fn(),
    };
    const client = new GeminiLiveClient(callbacks, [
      { sender: 'human', text: 'Previous question' },
      { sender: 'ai', text: 'Previous answer' },
    ]);
    client.connect('token/value');
    const socket = FakeWebSocket.instances[0]!;

    expect(socket.url).toContain('BidiGenerateContentConstrained');
    expect(socket.url).toContain('access_token=token%2Fvalue');

    socket.onopen?.();
    const setup = JSON.parse(socket.sent[0]!);
    expect(setup.setup.model).toBe('models/gemini-3.1-flash-live-preview');
    expect(setup.setup.generationConfig.responseModalities).toEqual(['AUDIO']);

    socket.emit({ setupComplete: {} });
    await Promise.resolve();
    const history = JSON.parse(socket.sent[1]!);
    expect(history.clientContent).toEqual({
      turns: [
        { role: 'user', parts: [{ text: 'Previous question' }] },
        { role: 'model', parts: [{ text: 'Previous answer' }] },
      ],
      turnComplete: false,
    });
    expect(doubles.start).toHaveBeenCalledTimes(1);
    expect(callbacks.onReady).toHaveBeenCalledTimes(1);

    doubles.captureOptions?.onAudioData(new Int16Array([1, -1]));
    expect(JSON.parse(socket.sent.at(-1)!).realtimeInput.audio.mimeType).toBe(
      'audio/pcm;rate=16000',
    );

    socket.emit({
      usageMetadata: {
        promptTokensDetails: [{ modality: 'AUDIO', tokenCount: 12 }],
        responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 8 }],
      },
      serverContent: { inputTranscription: { text: 'Hello Omi' } },
    });
    socket.emit({
      serverContent: {
        outputTranscription: { text: 'Hello there' },
        turnComplete: true,
      },
    });

    expect(callbacks.onExchange).toHaveBeenCalledWith('Hello Omi', 'Hello there');
    expect(callbacks.onUsage).toHaveBeenCalledWith(
      expect.objectContaining({ input_audio_tokens: 12, output_audio_tokens: 8 }),
    );
    client.stop();
  });

  it('persists the latest partial transcript when the user stops', () => {
    const callbacks = {
      onReady: vi.fn(),
      onLevel: vi.fn(),
      onTranscript: vi.fn(),
      onExchange: vi.fn(),
      onUsage: vi.fn(),
      onError: vi.fn(),
      onClose: vi.fn(),
    };
    const client = new GeminiLiveClient(callbacks, []);
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;
    socket.emit({
      serverContent: {
        inputTranscription: { text: 'Remember this unfinished turn' },
      },
    });

    client.stop();

    expect(callbacks.onExchange).toHaveBeenCalledWith(
      'Remember this unfinished turn',
      '',
    );
  });

  it('maps Gemini fallback token counts without inventing audio usage', () => {
    expect(
      geminiUsageReport({
        promptTokenCount: 14,
        candidatesTokenCount: 9,
        cachedContentTokenCount: 3,
      }),
    ).toEqual({
      input_text_tokens: 14,
      input_audio_tokens: 0,
      input_cached_tokens: 3,
      output_text_tokens: 9,
      output_audio_tokens: 0,
    });
  });
});
