import { createDeepgramTranscriber } from '../stt/deepgram';

class FakeSocket {
  readyState = 1;
  binaryType = 'arraybuffer';
  sent: unknown[] = [];
  closeCount = 0;
  onmessage: ((event: { data: string }) => void) | null = null;

  send(data: unknown) {
    this.sent.push(data);
  }

  close() {
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
    expect(socket.sent).toEqual([JSON.stringify({ type: 'CloseStream' })]);
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
    expect(socket.sent).toEqual([]);
    expect(socket.closeCount).toBe(1);
  });
});
