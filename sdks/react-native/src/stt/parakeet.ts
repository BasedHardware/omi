import type { StreamingTranscriber, TranscriptHandler } from './types';

export function parakeetWsUrl(apiUrl: string, sampleRate = 16000): string {
  let base = apiUrl.trim().replace(/\/+$/, '');
  base = base.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  return `${base}/v3/stream?sample_rate=${sampleRate}`;
}

export function createParakeetTranscriber(options: {
  apiUrl: string;
  sampleRate?: number;
  onTranscript: TranscriptHandler;
}): StreamingTranscriber {
  const sampleRate = options.sampleRate ?? 16000;
  const url = parakeetWsUrl(options.apiUrl, sampleRate);
  const ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';
  let ready = false;

  ws.onmessage = (event) => {
    if (typeof event.data !== 'string') return;
    try {
      const data = JSON.parse(event.data);
      if (data?.type === 'ready') {
        ready = true;
        return;
      }
      const text =
        data?.text ||
        data?.transcript ||
        (Array.isArray(data?.segments)
          ? data.segments.map((s: any) => s.text || s.transcript || '').filter(Boolean).join(' ')
          : '');
      if (text) options.onTranscript(text);
    } catch {
      // ignore
    }
  };

  return {
    appendPcm(chunk) {
      if (ready && ws.readyState === WebSocket.OPEN) {
        ws.send(chunk);
      }
    },
    stop() {
      try {
        if (ws.readyState === WebSocket.OPEN) ws.send('finalize');
        ws.close();
      } catch {
        // ignore
      }
    },
  };
}
