export type SttEngine = 'deepgram' | 'whisper' | 'parakeet';

export type TranscriptHandler = (text: string) => void;

export interface StreamingTranscriber {
  appendPcm(chunk: Uint8Array | ArrayBuffer): void;
  stop(): void;
}
