import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TranscriptionSocket } from '../transcriptionSocket';

vi.mock('../firebase', () => ({
  getIdToken: vi.fn().mockResolvedValue('test-token'),
  auth: { currentUser: { uid: 'web-owner' } },
}));
vi.mock('../clientDevice', () => ({
  getWebDeviceIdHash: vi.fn().mockResolvedValue('test-device'),
}));

// No real network: every WebSocket operation stays in this fake.
class FakeWebSocket {
  static current: FakeWebSocket;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  binaryType = '';
  send = vi.fn();
  close = vi.fn();
  constructor() {
    FakeWebSocket.current = this;
  }
  message(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

let client: TranscriptionSocket;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', FakeWebSocket);
});
afterEach(() => {
  client?.disconnect();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function connect() {
  const onServerBatch = vi.fn();
  const onSegment = vi.fn();
  client = new TranscriptionSocket({
    onServerBatch,
    onSegment,
    onConnected: vi.fn(),
    onDisconnected: vi.fn(),
    onError: vi.fn(),
  });
  await client.connect();
  const socket = FakeWebSocket.current;
  socket.onopen?.();
  socket.message({ type: 'auth_response', success: true });
  return { socket, onServerBatch, onSegment };
}

describe('server batch ready mode', () => {
  it('reports explicit batch, resets on a live ready, and still sends audio', async () => {
    const { socket, onServerBatch } = await connect();
    socket.message({ type: 'service_status', status: 'ready', server_batch_only: true });
    expect(onServerBatch).toHaveBeenLastCalledWith(true);
    const pcm = new Int16Array([1, 2, 3]);
    client.sendAudio(pcm);
    expect(socket.send).toHaveBeenLastCalledWith(pcm.buffer);
    socket.message({ type: 'service_status', status: 'ready', server_batch_only: false });
    expect(onServerBatch).toHaveBeenLastCalledWith(false);
    socket.message({ type: 'service_status', status: 'ready' });
    expect(onServerBatch).toHaveBeenLastCalledWith(false);
  });

  it('keeps deferred/legacy ready live and ignores unrelated statuses', async () => {
    const { socket, onServerBatch, onSegment } = await connect();
    socket.message({
      type: 'service_status',
      status: 'initiating',
      server_batch_only: true,
    });
    socket.message({
      type: 'service_status',
      status: 'stt_failed',
      server_batch_only: true,
    });
    expect(onServerBatch).not.toHaveBeenCalled();
    socket.message({ type: 'service_status', status: 'ready', local_preview: true });
    expect(onServerBatch).toHaveBeenLastCalledWith(false);
    socket.message({
      type: 'service_status',
      status: 'ready',
      server_batch_only: 'true',
    });
    expect(onServerBatch).toHaveBeenLastCalledWith(false);
    socket.message([{ id: 'live', text: 'Live words', speaker: 0 }]);
    expect(onSegment).toHaveBeenCalledWith(
      expect.objectContaining({ text: 'Live words' }),
    );
  });

  it('ignores a retired socket ready after reconnection', async () => {
    const { socket, onServerBatch } = await connect();
    client.disconnect();
    await client.connect();
    socket.message({ type: 'service_status', status: 'ready', server_batch_only: true });
    expect(onServerBatch).not.toHaveBeenCalled();
    FakeWebSocket.current.message({ type: 'service_status', status: 'ready' });
    expect(onServerBatch).toHaveBeenLastCalledWith(false);
  });
});
