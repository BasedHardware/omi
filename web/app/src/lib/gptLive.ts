import { createAudioCapture, type AudioCapture } from '@/lib/audioCapture';
import type { RealtimeUsageReport } from '@/lib/api';
import { PcmPlayer, appendChunk, pcmToBase64 } from '@/lib/geminiLive';

export const GPT_LIVE_MODEL = 'gpt-live-1';
export const GPT_LIVE_VOICE = 'marin';
export const GPT_LIVE_SAMPLE_RATE = 24000;

export const DEFAULT_GPT_LIVE_INSTRUCTIONS =
  'You are Omi, a concise and helpful voice assistant. Continue naturally from the conversation history when it is relevant.';

interface GptLiveUsageMetadata {
  input_tokens?: number;
  output_tokens?: number;
  input_token_details?: {
    text_tokens?: number;
    audio_tokens?: number;
    cached_tokens?: number;
  };
  output_token_details?: {
    text_tokens?: number;
    audio_tokens?: number;
  };
}

interface GptLiveMessage {
  type?: string;
  delta?: string;
  interrupted?: boolean;
  error?: string;
  message?: string;
  success?: boolean;
  usage?: GptLiveUsageMetadata;
  /** Nested event for a `response.event` envelope (turn lifecycle). */
  event?: GptLiveMessage;
}

export interface GptLiveClientCallbacks {
  onReady: () => void;
  onLevel: (level: number) => void;
  onInputTranscript: (text: string) => void;
  onOutputTranscript: (text: string) => void;
  onExchange: (humanText: string, aiText: string) => void;
  onUsage: (usage: RealtimeUsageReport) => void;
  onInterrupted: () => void;
  onError: (message: string) => void;
  onClose: () => void;
}

export interface GptLiveClientOptions extends GptLiveClientCallbacks {
  /**
   * Omi bearer token for the relay. Optional because the hook mints the
   * session first and passes it to `connect`; an explicit `relayUrl` wins when
   * a caller needs to point somewhere else.
   */
  token?: string;
  relayUrl?: string;
  /** System prompt sent as `session.start.session.instructions`. */
  instructions?: string;
}

function relayBaseUrl(): string {
  const wsBase = process.env.NEXT_PUBLIC_WS_BASE_URL;
  if (wsBase) return wsBase.replace(/\/$/, '');
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (apiBase) return apiBase.replace(/^http/, 'ws').replace(/\/$/, '');
  return 'wss://api.omi.me';
}

/**
 * Build the Omi relay URL. The Omi bearer token never travels in the query
 * string (WebSocket request targets, including query strings, are logged by the
 * access logger and ingress); the browser authenticates in the first WS message
 * instead (`{type:'auth', token}`), mirroring `transcriptionSocket.ts`.
 */
export function gptLiveRelayUrl(): string {
  return `${relayBaseUrl()}/v1/omni/relay?provider=gpt_live`;
}

function eventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Map the usage block on `session.closed` into the hub's report shape.
 *
 * The relay speaks OpenAI-style counts (modality split under
 * `input_token_details` / `output_token_details`); an aggregate-only block
 * falls back to the total without inventing an audio split.
 */
export function gptLiveUsageReport(usage: GptLiveUsageMetadata): RealtimeUsageReport {
  const input: NonNullable<GptLiveUsageMetadata['input_token_details']> =
    usage.input_token_details ?? {};
  const output: NonNullable<GptLiveUsageMetadata['output_token_details']> =
    usage.output_token_details ?? {};
  const inputText = input.text_tokens ?? 0;
  const inputAudio = input.audio_tokens ?? 0;
  const outputText = output.text_tokens ?? 0;
  const outputAudio = output.audio_tokens ?? 0;
  return {
    input_text_tokens: inputText + inputAudio > 0 ? inputText : usage.input_tokens ?? 0,
    input_audio_tokens: inputAudio,
    input_cached_tokens: input.cached_tokens ?? 0,
    output_text_tokens:
      outputText + outputAudio > 0 ? outputText : usage.output_tokens ?? 0,
    output_audio_tokens: outputAudio,
  };
}

export class GptLiveClient {
  private socket: WebSocket | null = null;
  private capture: AudioCapture | null = null;
  private player = new PcmPlayer();
  private humanText = '';
  private aiText = '';
  private usage: RealtimeUsageReport | null = null;
  private stopped = false;
  private connectionTimeout: number | null = null;
  /** Sends `session.start`; deferred until `auth_response` on the managed relay. */
  private sendStartFrame: (() => void) | null = null;

  constructor(private options: GptLiveClientOptions) {}

  connect(token = this.options.token ?? ''): void {
    this.stopped = false;
    const url = this.options.relayUrl ?? gptLiveRelayUrl();
    const socket = new WebSocket(url);
    this.socket = socket;
    this.connectionTimeout = window.setTimeout(
      () => this.fail('GPT Live took too long to connect'),
      15000,
    );
    const sendStart = (): void => {
      socket.send(
        JSON.stringify({
          type: 'session.start',
          event_id: eventId(),
          session: {
            model: GPT_LIVE_MODEL,
            instructions: this.options.instructions ?? DEFAULT_GPT_LIVE_INSTRUCTIONS,
            audio: {
              format: { type: 'audio/pcm', rate: GPT_LIVE_SAMPLE_RATE },
              output: { voice: GPT_LIVE_VOICE },
            },
          },
        }),
      );
    };
    this.sendStartFrame = sendStart;
    socket.onopen = () => {
      if (token) {
        // First-message auth: the bearer token must not ride the URL.
        socket.send(JSON.stringify({ type: 'auth', token }));
      } else {
        sendStart();
      }
    };
    socket.onmessage = (event) => this.handleMessage(String(event.data));
    socket.onerror = () => this.fail('GPT Live connection failed');
    socket.onclose = () => {
      this.capture?.stop();
      this.capture = null;
      this.player.close();
      if (!this.stopped) this.options.onError('GPT Live disconnected');
      this.options.onClose();
    };
  }

  pause(): void {
    this.capture?.pause();
  }

  resume(): void {
    this.capture?.resume();
  }

  stop(): void {
    this.stopped = true;
    this.flushExchange();
    if (this.connectionTimeout !== null) {
      window.clearTimeout(this.connectionTimeout);
      this.connectionTimeout = null;
    }
    this.capture?.stop();
    this.capture = null;
    this.player.close();
    this.sendStartFrame = null;
    const socket = this.socket;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'session.close' }));
    }
    socket?.close();
    this.socket = null;
  }

  private async startCapture(): Promise<void> {
    if (this.capture) return;
    const capture = createAudioCapture({
      mode: 'mic-only',
      sampleRate: GPT_LIVE_SAMPLE_RATE,
      onAudioData: (pcm) => {
        if (this.socket?.readyState !== WebSocket.OPEN) return;
        this.socket.send(
          JSON.stringify({
            type: 'session.input_audio.append',
            audio: pcmToBase64(pcm),
          }),
        );
      },
      onMicLevel: this.options.onLevel,
      onSystemLevel: () => undefined,
      onError: this.options.onError,
    });
    this.capture = capture;
    try {
      await capture.start();
      if (this.stopped || this.capture !== capture) {
        capture.stop();
        return;
      }
      this.options.onReady();
    } catch (error) {
      this.fail(error instanceof Error ? error.message : 'Microphone access failed');
    }
  }

  private handleMessage(raw: string): void {
    let message: GptLiveMessage;
    try {
      message = JSON.parse(raw) as GptLiveMessage;
    } catch {
      return;
    }
    switch (message.type) {
      case 'auth_response': {
        // Managed relay first-message auth. Only now is the session safe to open.
        if (message.success) {
          this.sendStartFrame?.();
        } else {
          this.fail('GPT Live authentication failed');
        }
        return;
      }
      case 'session.started': {
        if (this.connectionTimeout !== null) {
          window.clearTimeout(this.connectionTimeout);
          this.connectionTimeout = null;
        }
        void this.startCapture();
        return;
      }
      case 'session.output_audio.delta': {
        if (message.delta) this.player.play(message.delta);
        return;
      }
      case 'session.input_transcript.delta': {
        if (message.delta) {
          this.humanText = appendChunk(this.humanText, message.delta);
          this.options.onInputTranscript(this.humanText);
        }
        return;
      }
      case 'session.output_transcript.delta': {
        if (message.delta) {
          this.aiText = appendChunk(this.aiText, message.delta);
          this.options.onOutputTranscript(this.aiText);
        }
        return;
      }
      case 'response.event': {
        // Per-turn boundary. Without this the whole multi-turn session collapses
        // into one synthetic exchange flushed only at close.
        const nested = message.event ?? message;
        const nestedType = nested.type ?? '';
        if (nestedType === 'response.done' || nestedType === 'response.completed') {
          this.flushExchange();
        }
        return;
      }
      case 'session.closed': {
        if (message.usage) this.usage = gptLiveUsageReport(message.usage);
        this.stop();
        return;
      }
      case 'error': {
        this.options.onError(
          message.message ?? message.error ?? 'GPT Live encountered an error',
        );
        return;
      }
      case 'session.interrupted': {
        this.interrupt();
        return;
      }
      default: {
        if (message.interrupted) this.interrupt();
      }
    }
  }

  private interrupt(): void {
    this.aiText = '';
    this.player.interrupt();
    this.options.onOutputTranscript('');
    this.options.onInterrupted();
  }

  private flushExchange(): void {
    const humanText = this.humanText.trim();
    const aiText = this.aiText.trim();
    this.humanText = '';
    this.aiText = '';
    this.options.onInputTranscript('');
    this.options.onOutputTranscript('');
    if (humanText || aiText) this.options.onExchange(humanText, aiText);
    if (this.usage) this.options.onUsage(this.usage);
    this.usage = null;
  }

  private fail(message: string): void {
    this.options.onError(message);
    this.stop();
  }
}

export function createGptLiveClient(options: GptLiveClientOptions): GptLiveClient {
  return new GptLiveClient(options);
}
