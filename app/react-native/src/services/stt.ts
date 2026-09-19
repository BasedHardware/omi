export interface DeepgramMessage {
  channel?: { alternatives?: { transcript?: string; words?: { speaker?: number; word: string; start: number; end: number }[] }[] };
  is_final?: boolean;
}

export interface TranscriptSegment {
  text: string;
  speaker: string;
  start: number;
  end: number;
  isFinal: boolean;
}

export interface SttHandlers {
  onSegment: (seg: TranscriptSegment) => void;
  onOpen?: () => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

/**
 * Streaming STT client.
 *
 * SECURITY: this class intentionally does NOT build a provider URL from a
 * bundled API key. The caller passes an already-authorized websocket `url` —
 * normally the Omi backend STT proxy (`ENV.listenWsUrl`), which authenticates
 * with the short-lived user ID token and keeps provider credentials server-side.
 * For local development a caller may supply an ephemeral Deepgram URL out-of-band;
 * that token must never be committed or read from `expo.extra`.
 */
export class DeepgramStream {
  private ws: WebSocket | null = null;

  constructor(private handlers: SttHandlers, private url: string) {}

  connect(): void {
    if (!this.url) {
      this.handlers.onError?.(new Error('STT not configured: no authorized endpoint'));
      return;
    }
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch (e) {
      this.handlers.onError?.(e);
      return;
    }
    this.ws = ws;
    this.ws.binaryType = 'arraybuffer';
    this.ws.onopen = () => this.handlers.onOpen?.();
    this.ws.onerror = (ev) => this.handlers.onError?.(ev);
    this.ws.onclose = () => {
      this.ws = null;
      this.handlers.onClose?.();
    };
    this.ws.onmessage = (ev) => this.handleMessage(ev.data);
  }

  private handleMessage(data: string) {
    try {
      const msg = JSON.parse(data) as DeepgramMessage;
      const alt = msg.channel?.alternatives?.[0];
      if (!alt?.transcript) return;
      const speaker = alt.words?.[0]?.speaker ?? 0;
      this.handlers.onSegment({
        text: alt.transcript,
        speaker: `speaker_${speaker}`,
        start: alt.words?.[0]?.start ?? 0,
        end: alt.words?.[alt.words.length - 1]?.end ?? 0,
        isFinal: Boolean(msg.is_final),
      });
    } catch {
      /* ignore malformed frames */
    }
  }

  sendAudio(chunk: ArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(chunk);
  }

  close() {
    this.ws?.close();
    this.ws = null;
  }
}
