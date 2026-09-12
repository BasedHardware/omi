import { createDeepgramTranscriber } from '../stt/deepgram';

class FakeSocket {
  readyState = 1;
  binaryType = 'arraybuffer';
  sent: unknown[] = [];
  closeCount = 0;
  events: Array<'send' | 'close'> = [];
  onmessage: ((event: { data: string }) => void) | null = null;
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
}

describe('createDeepgramTranscriber stop', () => {
  test('sends CloseStream before closing the socket', () => {
    const socket = new FakeSocket();
    const transcriber = createDeepgramTranscriber({
      apiKey: 'synthetic',
      onTranscript: () => undefined,
      createWebSocket: () => socket as unknown as WebSocket,
    });
    transcriber.stop();
    expect(socket.events).toEqual(['send', 'close']);
    expect(socket.sent).toEqual([JSON.stringify({ type: 'CloseStream' })]);
    expect(socket.closeCount).toBe(1);
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
