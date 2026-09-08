import type { StreamingTranscriber, TranscriptHandler } from './types';

/**
 * Whisper is offline/local. Inject a runner (native module / whisper.rn / etc).
 * Feature-gated: no default native binary in JS package.
 */
export function createWhisperTranscriber(options: {
  /** Convert accumulated PCM16 LE mono 16kHz to transcript text. */
  runner: (pcm: Uint8Array) => Promise<string> | string;
  onTranscript: TranscriptHandler;
  /** Approx seconds of audio per decode batch. */
  batchSeconds?: number;
}): StreamingTranscriber {
  const batchBytes = (options.batchSeconds ?? 5) * 16000 * 2;
  let buffer = new Uint8Array(0);
  let stopped = false;
  let pending = Promise.resolve();

  function flush() {
    if (buffer.byteLength === 0) return;
    const pcm = buffer;
    buffer = new Uint8Array(0);
    const decode = async () => {
      const text = await options.runner(pcm);
      if (text) options.onTranscript(text);
    };
    // A failed batch must not prevent later accepted audio from being decoded.
    pending = pending.then(decode, decode);
    return pending;
  }

  return {
    appendPcm(chunk) {
      if (stopped) return;
      const incoming = chunk instanceof ArrayBuffer ? new Uint8Array(chunk) : chunk;
      const next = new Uint8Array(buffer.byteLength + incoming.byteLength);
      next.set(buffer, 0);
      next.set(incoming, buffer.byteLength);
      buffer = next;
      if (buffer.byteLength >= batchBytes) {
        void flush();
      }
    },
    stop() {
      if (stopped) return;
      stopped = true;
      void flush();
    },
  };
}
