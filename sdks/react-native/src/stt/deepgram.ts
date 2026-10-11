import type { StreamingTranscriber, TranscriptHandler } from './types';

/**
 * Deepgram live STT.
 * React Native and browser WebSocket implementations cannot attach Authorization
 * headers after construction, so callers must supply `createWebSocket`.
 */
export function createDeepgramTranscriber(options: {
  apiKey: string;
  sampleRate?: number;
  onTranscript: TranscriptHandler;
  createWebSocket: (url: string, headers: Record<string, string>) => WebSocket;
  /** Optional final-transcript drain after CloseStream. Default 0 (immediate close). */
  drainTimeoutMs?: number;
}): StreamingTranscriber {
  const sampleRate = options.sampleRate ?? 16000;
  const url =
    `wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US` +
    `&encoding=linear16&sample_rate=${sampleRate}&channels=1`;
  const headers = { Authorization: `Token ${options.apiKey}` };
  const ws = options.createWebSocket(url, headers);
  ws.binaryType = 'arraybuffer';
  let stopped = false;
  let finished = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const finish = () => {
    if (finished) return;
    finished = true;
    if (timer !== undefined) clearTimeout(timer);
    try {
      ws.close();
    } catch {
      // ignore
    }
  };
  ws.onmessage = (event) => {
    try {
      const data =
        typeof event.data === 'string' ? JSON.parse(event.data) : null;
      const transcript = data?.channel?.alternatives?.[0]?.transcript;
      if (transcript) options.onTranscript(transcript);
    } catch {
      // ignore parse errors
    }
  };

  return {
    appendPcm(chunk) {
      if (!stopped && ws.readyState === WebSocket.OPEN) {
        ws.send(chunk);
      }
    },
    stop() {
      if (stopped) return;
      stopped = true;
      const previousClose = ws.onclose;
      ws.onclose = (event) => {
        finish();
        if (typeof previousClose === 'function') previousClose.call(ws, event);
      };
      let sentClose = false;
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'CloseStream' }));
          sentClose = true;
        }
      } catch {
        // CloseStream is best-effort; still tear down the socket.
      }
      const drainTimeoutMs = options.drainTimeoutMs ?? 0;
      if (!sentClose || finished || drainTimeoutMs <= 0) {
        finish();
        return;
      }
      timer = setTimeout(finish, drainTimeoutMs);
    },
  };
}
