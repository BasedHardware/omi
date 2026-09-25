import { createAudioCapture, type AudioCapture } from '@/lib/audioCapture';
import type { RealtimeUsageReport } from '@/lib/api';

const GEMINI_LIVE_MODEL = 'models/gemini-3.1-flash-live-preview';
const GEMINI_LIVE_ENDPOINT =
  'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained';

interface GeminiLiveCallbacks {
  onReady: () => void;
  onLevel: (level: number) => void;
  onTranscript: (humanText: string, aiText: string) => void;
  onExchange: (humanText: string, aiText: string) => void;
  onUsage: (usage: RealtimeUsageReport) => void;
  onError: (message: string) => void;
  onClose: () => void;
}

interface GeminiHistoryMessage {
  sender: 'human' | 'ai';
  text: string;
}

interface GeminiUsageMetadata {
  promptTokenCount?: number;
  responseTokenCount?: number;
  candidatesTokenCount?: number;
  cachedContentTokenCount?: number;
  promptTokensDetails?: Array<{ modality?: string; tokenCount?: number }>;
  responseTokensDetails?: Array<{ modality?: string; tokenCount?: number }>;
}

interface GeminiServerContent {
  inputTranscription?: { text?: string };
  outputTranscription?: { text?: string };
  modelTurn?: {
    parts?: Array<{
      text?: string;
      inlineData?: { mimeType?: string; data?: string };
    }>;
  };
  interrupted?: boolean;
  turnComplete?: boolean;
}

interface GeminiMessage {
  setupComplete?: Record<string, never>;
  usageMetadata?: GeminiUsageMetadata;
  serverContent?: GeminiServerContent;
}

function appendChunk(current: string, chunk: string): string {
  if (!chunk) return current;
  if (!current) return chunk;
  if (/\s$/.test(current) || /^\s/.test(chunk)) return current + chunk;
  return `${current} ${chunk}`;
}

function pcmToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function splitUsage(details: GeminiUsageMetadata['promptTokensDetails']): {
  text: number;
  audio: number;
} {
  return (details ?? []).reduce(
    (total, detail) => {
      const count = detail.tokenCount ?? 0;
      if (detail.modality?.toUpperCase() === 'AUDIO') total.audio += count;
      else total.text += count;
      return total;
    },
    { text: 0, audio: 0 },
  );
}

export function geminiUsageReport(metadata: GeminiUsageMetadata): RealtimeUsageReport {
  const input = splitUsage(metadata.promptTokensDetails);
  const output = splitUsage(metadata.responseTokensDetails);
  return {
    input_text_tokens:
      input.text + input.audio > 0 ? input.text : (metadata.promptTokenCount ?? 0),
    input_audio_tokens: input.audio,
    input_cached_tokens: metadata.cachedContentTokenCount ?? 0,
    output_text_tokens:
      output.text + output.audio > 0
        ? output.text
        : (metadata.candidatesTokenCount ?? metadata.responseTokenCount ?? 0),
    output_audio_tokens: output.audio,
  };
}

class PcmPlayer {
  private context: AudioContext | null = null;
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();

  play(base64: string): void {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const samples = new Int16Array(bytes.buffer);
    const context = this.context ?? new AudioContext({ sampleRate: 24000 });
    this.context = context;
    const buffer = context.createBuffer(1, samples.length, 24000);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      channel[index] = samples[index]! / 0x8000;
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    source.onended = () => this.sources.delete(source);
    const start = Math.max(context.currentTime, this.nextStart);
    source.start(start);
    this.nextStart = start + buffer.duration;
    this.sources.add(source);
  }

  interrupt(): void {
    for (const source of this.sources) source.stop();
    this.sources.clear();
    this.nextStart = this.context?.currentTime ?? 0;
  }

  close(): void {
    this.interrupt();
    void this.context?.close();
    this.context = null;
  }
}

export class GeminiLiveClient {
  private socket: WebSocket | null = null;
  private capture: AudioCapture | null = null;
  private player = new PcmPlayer();
  private humanText = '';
  private aiText = '';
  private usage: RealtimeUsageReport | null = null;
  private stopped = false;
  private connectionTimeout: number | null = null;

  constructor(
    private callbacks: GeminiLiveCallbacks,
    private history: GeminiHistoryMessage[],
  ) {}

  connect(token: string): void {
    this.stopped = false;
    const url = `${GEMINI_LIVE_ENDPOINT}?access_token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);
    this.socket = socket;
    this.connectionTimeout = window.setTimeout(
      () => this.fail('Gemini Live took too long to connect'),
      15000,
    );
    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          setup: {
            model: GEMINI_LIVE_MODEL,
            generationConfig: {
              responseModalities: ['AUDIO'],
              speechConfig: {
                voiceConfig: { prebuiltVoiceConfig: { voiceName: 'Charon' } },
              },
            },
            systemInstruction: {
              parts: [
                {
                  text: 'You are Omi, a concise and helpful voice assistant. Continue naturally from the conversation history when it is relevant.',
                },
              ],
            },
            inputAudioTranscription: {},
            outputAudioTranscription: {},
            contextWindowCompression: { slidingWindow: {} },
          },
        }),
      );
    };
    socket.onmessage = (event) => this.handleMessage(String(event.data));
    socket.onerror = () => this.fail('Gemini Live connection failed');
    socket.onclose = () => {
      this.capture?.stop();
      this.capture = null;
      this.player.close();
      if (!this.stopped) this.callbacks.onError('Gemini Live disconnected');
      this.callbacks.onClose();
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
    this.socket?.close();
    this.socket = null;
  }

  private async startCapture(): Promise<void> {
    if (this.capture) return;
    if (this.history.length > 0 && this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(
        JSON.stringify({
          clientContent: {
            turns: this.history.map((message) => ({
              role: message.sender === 'human' ? 'user' : 'model',
              parts: [{ text: message.text }],
            })),
            turnComplete: false,
          },
        }),
      );
    }
    const capture = createAudioCapture({
      mode: 'mic-only',
      onAudioData: (pcm) => {
        if (this.socket?.readyState !== WebSocket.OPEN) return;
        this.socket.send(
          JSON.stringify({
            realtimeInput: {
              audio: { data: pcmToBase64(pcm), mimeType: 'audio/pcm;rate=16000' },
            },
          }),
        );
      },
      onMicLevel: this.callbacks.onLevel,
      onSystemLevel: () => undefined,
      onError: this.callbacks.onError,
    });
    this.capture = capture;
    try {
      await capture.start();
      if (this.stopped || this.capture !== capture) {
        capture.stop();
        return;
      }
      this.callbacks.onReady();
    } catch (error) {
      this.fail(error instanceof Error ? error.message : 'Microphone access failed');
    }
  }

  private handleMessage(raw: string): void {
    let message: GeminiMessage;
    try {
      message = JSON.parse(raw) as GeminiMessage;
    } catch {
      return;
    }
    if (message.setupComplete) {
      if (this.connectionTimeout !== null) {
        window.clearTimeout(this.connectionTimeout);
        this.connectionTimeout = null;
      }
      void this.startCapture();
      return;
    }
    if (message.usageMetadata) {
      this.usage = geminiUsageReport(message.usageMetadata);
    }
    const content = message.serverContent;
    if (!content) return;
    if (content.interrupted) {
      this.aiText = '';
      this.player.interrupt();
    }
    const humanChunk = content.inputTranscription?.text ?? '';
    if (humanChunk) this.humanText = appendChunk(this.humanText, humanChunk);
    const outputChunk = content.outputTranscription?.text ?? '';
    if (outputChunk) this.aiText = appendChunk(this.aiText, outputChunk);
    for (const part of content.modelTurn?.parts ?? []) {
      if (part.text && !outputChunk) this.aiText = appendChunk(this.aiText, part.text);
      if (part.inlineData?.mimeType?.includes('audio/pcm') && part.inlineData.data) {
        this.player.play(part.inlineData.data);
      }
    }
    this.callbacks.onTranscript(this.humanText, this.aiText);
    if (content.turnComplete) {
      this.flushExchange();
    }
  }

  private flushExchange(): void {
    const humanText = this.humanText.trim();
    const aiText = this.aiText.trim();
    this.humanText = '';
    this.aiText = '';
    this.callbacks.onTranscript('', '');
    if (humanText || aiText) this.callbacks.onExchange(humanText, aiText);
    if (this.usage) this.callbacks.onUsage(this.usage);
    this.usage = null;
  }

  private fail(message: string): void {
    this.callbacks.onError(message);
    this.stop();
  }
}
