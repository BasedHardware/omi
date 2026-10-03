import { createDeepgramTranscriber } from '../stt/deepgram';
import { createTranscriber } from '../stt';

class FakeSocket {
  readyState = 1;
  binaryType = 'arraybuffer';
  sent: unknown[] = [];
  closeCount = 0;
  events: Array<'send' | 'close'> = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { type: string }) => void) | null = null;
  sendError: Error | null = null;

  send(data: unknown) {
    this.events.push('send');
    this.sent.push(data);
    if (this.sendError) {
      throw this.sendError;
    }
  }

  close() {
    this.events.push('close');
    this.closeCount += 1;
    this.readyState = 3;
  }

  emitTranscript(text: string) {
    if (this.readyState !== 1) return;
    this.onmessage?.({
      data: JSON.stringify({
        channel: { alternatives: [{ transcript: text }] },
      }),
    });
  }

  serverClose() {
    this.readyState = 3;
    this.onclose?.({ type: 'close' });
  }
}

describe('createDeepgramTranscriber stop', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test('preserves immediate teardown when the factory drain option is omitted', () => {
    const socket = new FakeSocket();
    const onTranscript = jest.fn();
    const transcriber = createTranscriber('deepgram', {
      apiKey: 'synthetic',
      onTranscript,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    socket.emitTranscript('late words');
    expect(socket.events).toEqual(['send', 'close']);
    expect(socket.closeCount).toBe(1);
    expect(onTranscript).not.toHaveBeenCalled();
    expect(jest.getTimerCount()).toBe(0);
  });

  test('sends CloseStream and closes after an opted-in drain deadline', () => {
    const socket = new FakeSocket();
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      drainTimeoutMs: 5000,
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    expect(socket.events).toEqual(['send']);
    expect(socket.sent).toEqual([JSON.stringify({ type: 'CloseStream' })]);
    jest.advanceTimersByTime(4999);
    expect(socket.closeCount).toBe(0);
    jest.advanceTimersByTime(1);
    expect(socket.closeCount).toBe(1);
    expect(socket.events).toEqual(['send', 'close']);
  });

  test('delivers final transcripts while rejecting audio and repeated stop during drain', () => {
    const socket = new FakeSocket();
    const received: string[] = [];
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      drainTimeoutMs: 5000,
      onTranscript: (text) => received.push(text),
      createWebSocket: () => socket as unknown as WebSocket,
    });
    const pcm = new Uint8Array([1, 2]);
    transcriber.appendPcm(pcm);
    transcriber.stop();
    socket.emitTranscript('final words');
    expect(received).toEqual(['final words']);
    transcriber.appendPcm(new Uint8Array([3, 4]));
    transcriber.stop();
    expect(socket.sent).toEqual([pcm, JSON.stringify({ type: 'CloseStream' })]);
    socket.serverClose();
    expect(jest.getTimerCount()).toBe(0);
    jest.advanceTimersByTime(5000);
    expect(socket.closeCount).toBe(1);
  });

  test('forwards the configurable drain deadline through the public factory', () => {
    const socket = new FakeSocket();
    const transcriber = createTranscriber('deepgram', {
      apiKey: 'synthetic',
      drainTimeoutMs: 200,
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    jest.advanceTimersByTime(199);
    expect(socket.closeCount).toBe(0);
    jest.advanceTimersByTime(1);
    expect(socket.closeCount).toBe(1);
  });

  test('preserves an injected close handler and clears the drain timer', () => {
    const socket = new FakeSocket();
    const onClose = jest.fn();
    socket.onclose = onClose;
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      drainTimeoutMs: 5000,
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    socket.serverClose();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
  });

  test('allows explicitly selecting immediate teardown', () => {
    const socket = new FakeSocket();
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      drainTimeoutMs: 0,
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    expect(socket.events).toEqual(['send', 'close']);
    expect(jest.getTimerCount()).toBe(0);
  });

  test('closes the socket when CloseStream send fails', () => {
    const socket = new FakeSocket();
    socket.sendError = new Error('synthetic send failure');
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    expect(socket.events).toEqual(['send', 'close']);
    expect(socket.closeCount).toBe(1);
  });

  test('does not send CloseStream when the socket is already closed', () => {
    const socket = new FakeSocket();
    socket.readyState = 3;
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    expect(socket.events).toEqual(['close']);
    expect(socket.sent).toEqual([]);
    expect(socket.closeCount).toBe(1);
  });
});
