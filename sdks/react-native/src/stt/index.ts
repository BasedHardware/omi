import { createDeepgramTranscriber } from './deepgram';
import { createParakeetTranscriber } from './parakeet';
import { createWhisperTranscriber } from './whisper';
import type { SttEngine, StreamingTranscriber, TranscriptHandler } from './types';

export type { SttEngine, StreamingTranscriber, TranscriptHandler } from './types';
export { createDeepgramTranscriber } from './deepgram';
export { createParakeetTranscriber, parakeetWsUrl } from './parakeet';
export { createWhisperTranscriber } from './whisper';

export function createTranscriber(
  engine: SttEngine,
  options: {
    onTranscript: TranscriptHandler;
    apiKey?: string;
    apiUrl?: string;
    sampleRate?: number;
    whisperRunner?: (pcm: Uint8Array) => Promise<string> | string;
    createWebSocket?: (url: string, headers: Record<string, string>) => WebSocket;
  }
): StreamingTranscriber {
  switch (engine) {
    case 'deepgram':
      if (!options.apiKey) throw new Error('Deepgram apiKey required');
      return createDeepgramTranscriber({
        apiKey: options.apiKey,
        sampleRate: options.sampleRate,
        onTranscript: options.onTranscript,
        createWebSocket: options.createWebSocket,
      });
    case 'parakeet': {
      const apiUrl = options.apiUrl || (globalThis as any)?.process?.env?.HOSTED_PARAKEET_API_URL;
      if (!apiUrl) throw new Error('Parakeet apiUrl or HOSTED_PARAKEET_API_URL required');
      return createParakeetTranscriber({
        apiUrl,
        sampleRate: options.sampleRate,
        onTranscript: options.onTranscript,
      });
    }
    case 'whisper':
      if (!options.whisperRunner) {
        throw new Error('Whisper requires whisperRunner (feature-gated local model)');
      }
      return createWhisperTranscriber({
        runner: options.whisperRunner,
        onTranscript: options.onTranscript,
      });
    default:
      throw new Error(`Unknown STT engine: ${engine}`);
  }
}
