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
}): StreamingTranscriber {
  const sampleRate = options.sampleRate ?? 16000;
  const url =
    `wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US` +
    `&encoding=linear16&sample_rate=${sampleRate}&channels=1`;
  const headers = { Authorization: `Token ${options.apiKey}` };
  const ws = options.createWebSocket(url, headers);
  ws.binaryType = 'arraybuffer';
  ws.onmessage = (event) => {
    try {
      const data = typeof event.data === 'string' ? JSON.parse(event.data) : null;
      const transcript = data?.channel?.alternatives?.[0]?.transcript;
      if (transcript) options.onTranscript(transcript);
    } catch {
      // ignore parse errors
    }
  };

  return {
    appendPcm(chunk) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk);
      }
    },
    stop() {
      try {
        ws.close();
      } catch {
        // ignore
      }
    },
  };
}
