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

const { GptLiveClient, gptLiveUsageReport } = await import('@/lib/gptLive');

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

class FakeAudioContext {
  static sources = 0;
  currentTime = 0;
  destination = {};
  createBuffer(_channels: number, length: number) {
    return {
      duration: length / 24000,
      getChannelData: () => new Float32Array(length),
    };
  }
  createBufferSource() {
    FakeAudioContext.sources += 1;
    return {
      buffer: null as unknown,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      onended: null as null | (() => void),
    };
  }
  close() {}
}

function callbacks() {
  return {
    onReady: vi.fn(),
    onLevel: vi.fn(),
    onInputTranscript: vi.fn(),
    onOutputTranscript: vi.fn(),
    onExchange: vi.fn(),
    onUsage: vi.fn(),
    onInterrupted: vi.fn(),
    onError: vi.fn(),
    onClose: vi.fn(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  doubles.captureOptions = null;
  FakeWebSocket.instances = [];
  FakeAudioContext.sources = 0;
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.stubGlobal('AudioContext', FakeAudioContext);
});

describe('GptLiveClient', () => {
  it('speaks the relay GPT-Live protocol, streams 24kHz audio, and commits turns', async () => {
    const handlers = callbacks();
    const client = new GptLiveClient({
      ...handlers,
      instructions: 'You are Omi.',
    });
    client.connect('token/value');
    const socket = FakeWebSocket.instances[0]!;

    expect(socket.url).toContain('/v1/omni/relay');
    expect(socket.url).toContain('provider=gpt_live');
    // The bearer token must never appear in the WebSocket URL.
    expect(socket.url).not.toContain('token');
    expect(socket.url).not.toContain('token%2Fvalue');

    socket.onopen?.();
    // First-message auth before any session frame.
    expect(JSON.parse(socket.sent[0]!)).toEqual({ type: 'auth', token: 'token/value' });
    socket.emit({ type: 'auth_response', success: true });
    const start = JSON.parse(socket.sent[1]!);
    expect(start.type).toBe('session.start');
    expect(start.event_id).toBeTruthy();
    expect(start.session.model).toBe('gpt-live-1');
    expect(start.session.instructions).toBe('You are Omi.');
    expect(start.session.audio).toEqual({
      format: { type: 'audio/pcm', rate: 24000 },
      output: { voice: 'marin' },
    });

    socket.emit({ type: 'session.started', session: { id: 'gpt-session-1' } });
    await Promise.resolve();
    expect(doubles.start).toHaveBeenCalledTimes(1);
    expect(handlers.onReady).toHaveBeenCalledTimes(1);

    doubles.captureOptions?.onAudioData(new Int16Array([1, -1]));
    const audio = JSON.parse(socket.sent.at(-1)!);
    expect(audio.type).toBe('session.input_audio.append');
    expect(typeof audio.audio).toBe('string');

    socket.emit({ type: 'session.input_transcript.delta', delta: 'Hello Omi' });
    expect(handlers.onInputTranscript).toHaveBeenLastCalledWith('Hello Omi');

    socket.emit({ type: 'session.output_transcript.delta', delta: 'Hello there' });
    expect(handlers.onOutputTranscript).toHaveBeenLastCalledWith('Hello there');

    socket.emit({ type: 'session.output_audio.delta', delta: 'AAE=' });
    expect(FakeAudioContext.sources).toBe(1);

    socket.emit({
      type: 'session.closed',
      usage: {
        input_tokens: 14,
        output_tokens: 9,
        input_token_details: { text_tokens: 10, audio_tokens: 4, cached_tokens: 3 },
        output_token_details: { text_tokens: 7, audio_tokens: 2 },
      },
    });

    expect(handlers.onExchange).toHaveBeenCalledWith('Hello Omi', 'Hello there');
    expect(handlers.onUsage).toHaveBeenCalledWith({
      input_text_tokens: 10,
      input_audio_tokens: 4,
      input_cached_tokens: 3,
      output_text_tokens: 7,
      output_audio_tokens: 2,
    });
    client.stop();
  });

  it('flushes one exchange at each response boundary instead of only at close', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;

    socket.emit({ type: 'session.input_transcript.delta', delta: 'First question' });
    socket.emit({ type: 'session.output_transcript.delta', delta: 'First answer' });
    socket.emit({ type: 'response.event', event: { type: 'response.done' } });
    expect(handlers.onExchange).toHaveBeenNthCalledWith(
      1,
      'First question',
      'First answer',
    );

    socket.emit({ type: 'session.input_transcript.delta', delta: 'Second question' });
    socket.emit({ type: 'session.output_transcript.delta', delta: 'Second answer' });
    socket.emit({ type: 'response.event', event: { type: 'response.completed' } });
    expect(handlers.onExchange).toHaveBeenNthCalledWith(
      2,
      'Second question',
      'Second answer',
    );
    expect(handlers.onExchange).toHaveBeenCalledTimes(2);
    client.stop();
  });

  it('closes the session and persists the latest partial transcript on stop', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;
    socket.emit({
      type: 'session.input_transcript.delta',
      delta: 'Remember this unfinished turn',
    });

    client.stop();

    expect(handlers.onExchange).toHaveBeenCalledWith('Remember this unfinished turn', '');
    expect(socket.sent.some((frame) => frame.includes('"session.close"'))).toBe(true);
  });

  it('interrupts playback and clears assistant text on an interrupt event', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;
    socket.emit({ type: 'session.output_transcript.delta', delta: 'Half a sentence' });

    socket.emit({ type: 'session.interrupted' });

    expect(handlers.onInterrupted).toHaveBeenCalledTimes(1);
    expect(handlers.onOutputTranscript).toHaveBeenLastCalledWith('');
    client.stop();
  });

  it('treats an error frame as fatal: reports the message and stops the session', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;

    socket.emit({ type: 'error', error: 'boom' });

    expect(handlers.onError).toHaveBeenCalledWith('boom');
    // `fail` tears the session down (sends session.close).
    expect(socket.sent.some((frame) => frame.includes('"session.close"'))).toBe(true);
    client.stop();
  });

  it('normalizes a non-string error frame instead of reporting undefined', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;

    socket.emit({ type: 'error', error: { code: 'bad' } as unknown as string });

    expect(handlers.onError).toHaveBeenCalledWith('GPT Live encountered an error');
    client.stop();
  });

  it('waits out a brief usage grace before the hard close', () => {
    vi.useFakeTimers();
    try {
      const handlers = callbacks();
      const client = new GptLiveClient({ ...handlers });
      client.connect('token');
      const socket = FakeWebSocket.instances[0]!;
      const close = vi.spyOn(socket, 'close');

      client.stop();
      expect(close).not.toHaveBeenCalled(); // still listening for session.closed

      vi.advanceTimersByTime(400);
      expect(close).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('captures session.closed usage on stop and closes promptly', () => {
    const handlers = callbacks();
    const client = new GptLiveClient({ ...handlers });
    client.connect('token');
    const socket = FakeWebSocket.instances[0]!;

    client.stop();
    socket.emit({
      type: 'session.closed',
      usage: { input_tokens: 3, output_tokens: 2 },
    });

    expect(handlers.onUsage).toHaveBeenCalledWith(
      expect.objectContaining({ input_text_tokens: 3, output_text_tokens: 2 }),
    );
    expect(handlers.onClose).toHaveBeenCalled();
  });

  it('clears the connect timeout when the socket closes early', () => {
    vi.useFakeTimers();
    try {
      const handlers = callbacks();
      const client = new GptLiveClient({ ...handlers });
      client.connect('token');
      const socket = FakeWebSocket.instances[0]!;

      socket.onclose?.();
      expect(handlers.onError).toHaveBeenCalledWith('GPT Live disconnected');

      // The 15s connect timeout must not fire a second error after close.
      vi.advanceTimersByTime(20000);
      expect(handlers.onError).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('maps aggregate-only GPT-Live usage without inventing audio tokens', () => {
    expect(
      gptLiveUsageReport({
        input_tokens: 14,
        output_tokens: 9,
        input_token_details: { cached_tokens: 3 },
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
