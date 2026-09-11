import {LiveUnsupportedError, type GeminiLiveSession} from './liveClient';
import type {LiveVoiceCallbacks, LiveVoicePhase} from './liveWebRtc';

// Minimal Gemini Live WebSocket runtime. Adapted from main's geminiLive.ts
// setup/PCM patterns only — no transcript UI, usage reporting, or history.
export type LiveGeminiScope = {
  WebSocket: new (url: string) => LiveGeminiSocket;
  AudioContext?: new (options?: {sampleRate?: number}) => LiveAudioContext;
  webkitAudioContext?: new (options?: {
    sampleRate?: number;
  }) => LiveAudioContext;
  navigator?: {
    mediaDevices?: {
      getUserMedia(constraints: {audio: boolean}): Promise<LiveMediaStream>;
    };
  };
};

type LiveGeminiSocket = {
  readyState: number;
  send(data: string): void;
  close(): void;
  addEventListener(
    type: 'open' | 'message' | 'error' | 'close',
    listener: (event: {data?: unknown}) => void,
  ): void;
  removeEventListener(
    type: 'open' | 'message' | 'error' | 'close',
    listener: (event: {data?: unknown}) => void,
  ): void;
};

type LiveMediaStream = {
  getTracks(): Array<{stop(): void}>;
};

type LiveAudioContext = {
  sampleRate: number;
  currentTime: number;
  state: string;
  destination: unknown;
  createMediaStreamSource(stream: LiveMediaStream): {
    connect(node: unknown): void;
  };
  createScriptProcessor(
    bufferSize: number,
    inputChannels: number,
    outputChannels: number,
  ): {
    onaudioprocess:
      | ((event: {
          inputBuffer: {getChannelData(channel: number): Float32Array};
        }) => void)
      | null;
    connect(node: unknown): void;
    disconnect(): void;
  };
  createBuffer(
    channels: number,
    length: number,
    sampleRate: number,
  ): {
    getChannelData(channel: number): Float32Array;
    duration: number;
  };
  createBufferSource(): {
    buffer: unknown;
    connect(node: unknown): void;
    start(when?: number): void;
    stop(): void;
    onended: (() => void) | null;
  };
  resume(): Promise<void>;
  close(): Promise<void>;
};

const OPEN = 1;

export function resolveLiveGeminiScope(): LiveGeminiScope | null {
  const scope = globalThis as unknown as Partial<LiveGeminiScope>;
  if (typeof scope.WebSocket !== 'function') return null;
  if (
    typeof scope.AudioContext !== 'function' &&
    typeof scope.webkitAudioContext !== 'function'
  ) {
    return null;
  }
  if (typeof scope.navigator?.mediaDevices?.getUserMedia !== 'function') {
    return null;
  }
  return scope as LiveGeminiScope;
}

function pcmToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary);
}

function base64ToPcm(base64: string): Int16Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

class PcmPlayer {
  private context: LiveAudioContext | null = null;
  private nextStart = 0;
  private sources = new Set<{stop(): void}>();

  constructor(
    private readonly AudioContextCtor: new (options?: {
      sampleRate?: number;
    }) => LiveAudioContext,
  ) {}

  play(base64: string): void {
    const samples = base64ToPcm(base64);
    const context =
      this.context ?? new this.AudioContextCtor({sampleRate: 24000});
    this.context = context;
    const buffer = context.createBuffer(1, samples.length, 24000);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) {
      channel[i] = samples[i]! / 0x8000;
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
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {}
    }
    this.sources.clear();
    this.nextStart = this.context?.currentTime ?? 0;
  }

  close(): void {
    this.interrupt();
    void this.context?.close();
    this.context = null;
  }
}

export class LiveGeminiSession {
  private socket: LiveGeminiSocket | null = null;
  private microphone: LiveMediaStream | null = null;
  private audioContext: LiveAudioContext | null = null;
  private processor: {
    onaudioprocess:
      | ((event: {
          inputBuffer: {getChannelData(channel: number): Float32Array};
        }) => void)
      | null;
    disconnect(): void;
  } | null = null;
  private player: PcmPlayer | null = null;
  private closed = false;
  private connectionTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly scope: LiveGeminiScope,
    private readonly mint: () => Promise<GeminiLiveSession>,
    private readonly callbacks: LiveVoiceCallbacks = {},
  ) {}

  async start(): Promise<void> {
    if (this.closed) return;
    this.callbacks.onPhase?.('connecting');
    try {
      const session = await this.mint();
      if (this.closed) return;
      this.callbacks.onSessionId?.(session.sessionId);
      const AudioContextCtor =
        this.scope.AudioContext ?? this.scope.webkitAudioContext;
      if (AudioContextCtor === undefined) {
        throw new LiveUnsupportedError(
          'Gemini Live needs Web Audio on this device.',
        );
      }
      this.player = new PcmPlayer(AudioContextCtor);
      const url = `${session.url}?access_token=${encodeURIComponent(
        session.token,
      )}`;
      const socket = new this.scope.WebSocket(url);
      this.socket = socket;
      this.connectionTimer = setTimeout(() => {
        this.fail('Gemini Live took too long to connect');
      }, 15_000);
      socket.addEventListener('open', () => {
        socket.send(
          JSON.stringify({
            setup: {
              model: session.model,
              generationConfig: {
                responseModalities: ['AUDIO'],
                speechConfig: {
                  voiceConfig: {
                    prebuiltVoiceConfig: {voiceName: 'Charon'},
                  },
                },
              },
              systemInstruction: {
                parts: [
                  {
                    text: 'You are Omi, a concise and helpful voice assistant. Keep spoken replies short.',
                  },
                ],
              },
              inputAudioTranscription: {},
              outputAudioTranscription: {},
              contextWindowCompression: {slidingWindow: {}},
            },
          }),
        );
      });
      socket.addEventListener('message', event => {
        this.handleMessage(String(event.data ?? ''));
      });
      socket.addEventListener('error', () => {
        this.fail('Gemini Live connection failed');
      });
      socket.addEventListener('close', () => {
        if (!this.closed) {
          this.callbacks.onPhase?.('closed');
        }
        this.dispose();
      });
    } catch (error) {
      if (!this.closed) {
        this.callbacks.onPhase?.(
          'error',
          error instanceof Error && error.message.length > 0
            ? error.message
            : 'Gemini Live failed',
        );
      }
      this.dispose();
    }
  }

  stop(): void {
    if (this.closed) return;
    this.callbacks.onPhase?.('stopping');
    this.callbacks.onPhase?.('closed');
    this.dispose();
  }

  private async startCapture(): Promise<void> {
    const mediaDevices = this.scope.navigator?.mediaDevices;
    const AudioContextCtor =
      this.scope.AudioContext ?? this.scope.webkitAudioContext;
    if (mediaDevices === undefined || AudioContextCtor === undefined) {
      throw new LiveUnsupportedError(
        'Gemini Live needs microphone streaming on this device.',
      );
    }
    const microphone = await mediaDevices.getUserMedia({audio: true});
    if (this.closed) {
      for (const track of microphone.getTracks()) track.stop();
      return;
    }
    this.microphone = microphone;
    const context = new AudioContextCtor({sampleRate: 16000});
    this.audioContext = context;
    if (context.state === 'suspended') {
      await context.resume();
    }
    const source = context.createMediaStreamSource(microphone);
    // ScriptProcessor is deprecated but widely available; keep the Gemini
    // path minimal without pulling in a separate AudioWorklet bundle.
    const processor = context.createScriptProcessor(4096, 1, 1);
    this.processor = processor;
    processor.onaudioprocess = event => {
      const socket = this.socket;
      if (socket === null || socket.readyState !== OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, input[i]!));
        pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      socket.send(
        JSON.stringify({
          realtimeInput: {
            audio: {
              data: pcmToBase64(pcm),
              mimeType: 'audio/pcm;rate=16000',
            },
          },
        }),
      );
    };
    source.connect(processor);
    processor.connect(context.destination);
    this.callbacks.onPhase?.('live');
  }

  private handleMessage(raw: string): void {
    let message: {
      setupComplete?: unknown;
      serverContent?: {
        interrupted?: boolean;
        modelTurn?: {
          parts?: Array<{
            inlineData?: {mimeType?: string; data?: string};
          }>;
        };
      };
    };
    try {
      message = JSON.parse(raw) as typeof message;
    } catch {
      return;
    }
    if (message.setupComplete !== undefined) {
      if (this.connectionTimer !== null) {
        clearTimeout(this.connectionTimer);
        this.connectionTimer = null;
      }
      void this.startCapture().catch(error => {
        this.fail(
          error instanceof Error ? error.message : 'Microphone access failed',
        );
      });
      return;
    }
    const content = message.serverContent;
    if (content === undefined) return;
    if (content.interrupted) {
      this.player?.interrupt();
    }
    for (const part of content.modelTurn?.parts ?? []) {
      if (
        part.inlineData?.mimeType?.includes('audio/pcm') &&
        typeof part.inlineData.data === 'string'
      ) {
        this.player?.play(part.inlineData.data);
      }
    }
    this.callbacks.onEvent?.(message);
  }

  private fail(detail: string): void {
    if (this.closed) return;
    this.callbacks.onPhase?.('error', detail);
    this.dispose();
  }

  private dispose(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.connectionTimer !== null) {
      clearTimeout(this.connectionTimer);
      this.connectionTimer = null;
    }
    const processor = this.processor;
    this.processor = null;
    if (processor !== null) {
      try {
        processor.onaudioprocess = null;
        processor.disconnect();
      } catch {}
    }
    const microphone = this.microphone;
    this.microphone = null;
    if (microphone !== null) {
      for (const track of microphone.getTracks()) track.stop();
    }
    const audioContext = this.audioContext;
    this.audioContext = null;
    if (audioContext !== null) {
      void audioContext.close();
    }
    this.player?.close();
    this.player = null;
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      try {
        socket.close();
      } catch {}
    }
  }
}

export type {LiveVoicePhase};
