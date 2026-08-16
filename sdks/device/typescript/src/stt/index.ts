export type SttEngine = 'deepgram' | 'whisper' | 'parakeet';
export type TranscriptHandler = (text: string) => void;
export interface StreamingTranscriber {
  appendPcm(chunk: Uint8Array | ArrayBuffer): void;
  stop(): void;
}

export function parakeetWsUrl(apiUrl: string, sampleRate = 16000): string {
  let base = apiUrl.trim().replace(/\/+$/, '');
  base = base.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  return `${base}/v3/stream?sample_rate=${sampleRate}`;
}

export function deepgramWsUrl(sampleRate = 16000): string {
  return (
    `wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US` +
    `&encoding=linear16&sample_rate=${sampleRate}&channels=1`
  );
}

export function createDeepgramTranscriber(opts: {
  sampleRate?: number;
  onTranscript: TranscriptHandler;
  /** Header-capable authenticated WebSocket factory (or an authenticated proxy).
   *  The factory owns Deepgram authentication so credentials never enter the URL. */
  createWebSocket: (url: string) => WebSocket;
}): StreamingTranscriber {
  if (!opts.createWebSocket) throw new Error('Deepgram requires createWebSocket');
  const url = deepgramWsUrl(opts.sampleRate ?? 16000);
  const ws = opts.createWebSocket(url);
  ws.binaryType = 'arraybuffer';
  ws.onmessage = (event: MessageEvent) => {
    try {
      const data = typeof event.data === 'string' ? JSON.parse(event.data) : null;
      const t = data?.channel?.alternatives?.[0]?.transcript;
      if (t) opts.onTranscript(t);
    } catch { /* ignore */ }
  };
  return {
    appendPcm(chunk) {
      if (ws.readyState === 1) ws.send(chunk as any);
    },
    stop() {
      try { ws.close(); } catch { /* ignore */ }
    },
  };
}

export function createParakeetTranscriber(opts: {
  apiUrl: string;
  sampleRate?: number;
  onTranscript: TranscriptHandler;
  WebSocketImpl?: typeof WebSocket;
}): StreamingTranscriber {
  const WS = opts.WebSocketImpl ?? WebSocket;
  const url = parakeetWsUrl(opts.apiUrl, opts.sampleRate ?? 16000);
  const ws = new WS(url);
  ws.binaryType = 'arraybuffer';
  let ready = false;
  ws.onmessage = (event: MessageEvent) => {
    if (typeof event.data !== 'string') return;
    try {
      const data = JSON.parse(event.data);
      if (data?.type === 'ready') { ready = true; return; }
      const text =
        data?.text ||
        data?.transcript ||
        (Array.isArray(data?.segments)
          ? data.segments.map((s: any) => s.text || s.transcript || '').filter(Boolean).join(' ')
          : '');
      if (text) opts.onTranscript(text);
    } catch { /* ignore */ }
  };
  return {
    appendPcm(chunk) {
      if (ready && ws.readyState === WS.OPEN) ws.send(chunk as any);
    },
    stop() {
      try {
        if (ws.readyState === WS.OPEN) ws.send('finalize');
        ws.close();
      } catch { /* ignore */ }
    },
  };
}

export function createWhisperTranscriber(opts: {
  runner: (pcm: Uint8Array) => Promise<string> | string;
  onTranscript: TranscriptHandler;
  batchSeconds?: number;
}): StreamingTranscriber {
  const batchBytes = (opts.batchSeconds ?? 5) * 16000 * 2;
  let buffer = new Uint8Array(0);
  let stopped = false;
  async function flush(deliverWhenStopped = false) {
    if (!buffer.byteLength) return;
    const pcm = buffer;
    buffer = new Uint8Array(0);
    const text = await opts.runner(pcm);
    if (text && (!stopped || deliverWhenStopped)) opts.onTranscript(text);
  }
  return {
    appendPcm(chunk) {
      if (stopped) return;
      const incoming = chunk instanceof ArrayBuffer ? new Uint8Array(chunk) : chunk;
      const next = new Uint8Array(buffer.byteLength + incoming.byteLength);
      next.set(buffer, 0);
      next.set(incoming, buffer.byteLength);
      buffer = next;
      if (buffer.byteLength >= batchBytes) void flush();
    },
    stop() {
      stopped = true;
      void flush(true);
    },
  };
}

export function createTranscriber(
  engine: SttEngine,
  opts: {
    onTranscript: TranscriptHandler;
    apiKey?: string;
    apiUrl?: string;
    sampleRate?: number;
    whisperRunner?: (pcm: Uint8Array) => Promise<string> | string;
    WebSocketImpl?: typeof WebSocket;
    createWebSocket?: (url: string) => WebSocket;
  }
): StreamingTranscriber {
  if (engine === 'deepgram') {
    if (!opts.createWebSocket) throw new Error('Deepgram requires createWebSocket');
    return createDeepgramTranscriber({
      sampleRate: opts.sampleRate,
      onTranscript: opts.onTranscript,
      createWebSocket: opts.createWebSocket,
    });
  }
  if (engine === 'parakeet') {
    const apiUrl = opts.apiUrl || (globalThis as any)?.process?.env?.HOSTED_PARAKEET_API_URL;
    if (!apiUrl) throw new Error('Parakeet apiUrl required');
    return createParakeetTranscriber({ ...opts, apiUrl } as any);
  }
  if (engine === 'whisper') {
    if (!opts.whisperRunner) throw new Error('Whisper requires whisperRunner');
    return createWhisperTranscriber({ runner: opts.whisperRunner, onTranscript: opts.onTranscript });
  }
  throw new Error(`Unknown engine ${engine}`);
}
