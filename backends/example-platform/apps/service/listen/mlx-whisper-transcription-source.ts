// domain-pending(DIV-DOMCORE-012)

import type {
  TranscriptionConnection,
  TranscriptionEmission,
  TranscriptionSource,
} from "./transcription-source";

export const PCM16_TRANSCRIPTION_CODECS = Object.freeze(["pcm16", "linear16"]);
export const DEFAULT_MLX_WHISPER_WINDOW_SECONDS = 3;
export const DEFAULT_MLX_WHISPER_MIN_FLUSH_SECONDS = 0.5;
export const DEFAULT_MLX_WHISPER_SILENCE_SECONDS = 0.4;
export const DEFAULT_MLX_WHISPER_IDLE_FLUSH_MS = 750;
const BYTES_PER_PCM16_SAMPLE = 2;
const SILENCE_RMS_THRESHOLD = 400;
const READY_TIMEOUT_MS = 60_000;
const DISPOSE_KILL_MS = 1_000;

export class UnsupportedTranscriptionCodecError extends Error {
  readonly codec: string;
  constructor(codec: string) {
    super(`unsupported transcription codec: ${codec}`);
    this.name = "UnsupportedTranscriptionCodecError";
    this.codec = codec;
  }
}

export class UnsupportedTranscriptionFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedTranscriptionFormatError";
  }
}

export interface MlxWhisperTranscribeRequest {
  readonly pcm: Uint8Array;
  readonly sampleRate: number;
  readonly channels: number;
}

export interface MlxWhisperTranscribeResult {
  readonly text: string;
}

export interface MlxWhisperEngine {
  readonly pid: number | null;
  waitUntilReady(): Promise<void>;
  transcribe(request: MlxWhisperTranscribeRequest): Promise<MlxWhisperTranscribeResult>;
  dispose(): Promise<void>;
}

export interface MlxWhisperSubprocessOptions {
  readonly pythonPath: string;
  readonly workerPath: string;
  readonly model: string;
  readonly hfHome?: string;
  readonly readyTimeoutMs?: number;
}

export interface MlxWhisperTranscriptionSourceOptions {
  readonly engine?: MlxWhisperEngine;
  readonly subprocess?: MlxWhisperSubprocessOptions;
  readonly windowSeconds?: number;
  readonly minFlushSeconds?: number;
  readonly silenceFlushSeconds?: number | null;
  readonly idleFlushMs?: number | null;
}

export interface MlxWhisperTranscriptionSource extends TranscriptionSource {
  readonly engine: MlxWhisperEngine;
  dispose(): Promise<void>;
}

const isPcm16Codec = (codec: string): boolean =>
  (PCM16_TRANSCRIPTION_CODECS as readonly string[]).includes(codec);

const concatBytes = (left: Uint8Array, right: Uint8Array): Uint8Array => {
  if (left.byteLength === 0) return right;
  if (right.byteLength === 0) return left;
  const next = new Uint8Array(left.byteLength + right.byteLength);
  next.set(left, 0);
  next.set(right, left.byteLength);
  return next;
};

const tailIsSilent = (pcm: Uint8Array, channels: number, sampleCount: number): boolean => {
  const frameBytes = BYTES_PER_PCM16_SAMPLE * channels;
  const needed = sampleCount * frameBytes;
  if (pcm.byteLength < needed) return false;
  const view = new DataView(pcm.buffer, pcm.byteOffset + pcm.byteLength - needed, needed);
  let sumSquares = 0;
  const samples = sampleCount * channels;
  for (let index = 0; index < samples; index += 1) {
    const sample = view.getInt16(index * BYTES_PER_PCM16_SAMPLE, true);
    sumSquares += sample * sample;
  }
  return Math.sqrt(sumSquares / samples) < SILENCE_RMS_THRESHOLD;
};

export const createSubprocessMlxWhisperEngine = (
  options: MlxWhisperSubprocessOptions,
): MlxWhisperEngine => {
  const readyTimeoutMs = options.readyTimeoutMs ?? READY_TIMEOUT_MS;
  const env: Record<string, string> = {
    PATH: process.env.PATH ?? "/usr/bin:/bin:/usr/sbin:/sbin",
    PYTHONUNBUFFERED: "1",
    HF_HUB_OFFLINE: "1",
    HF_HUB_DISABLE_PROGRESS_BARS: "1",
    TQDM_DISABLE: "1",
  };
  if (process.env.HOME) env.HOME = process.env.HOME;
  if (process.env.LANG) env.LANG = process.env.LANG;
  if (options.hfHome) env.HF_HOME = options.hfHome;

  const proc = Bun.spawn([
    options.pythonPath,
    options.workerPath,
    "--model",
    options.model,
  ], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "inherit",
    env,
  });

  let disposed = false;
  let requestId = 0;
  let stdoutBuffer = "";
  const pending = new Map<string, {
    readonly resolve: (result: MlxWhisperTranscribeResult) => void;
    readonly reject: (error: unknown) => void;
  }>();

  const failPending = (error: unknown): void => {
    for (const waiter of pending.values()) waiter.reject(error);
    pending.clear();
  };

  let resolveReady: () => void = () => {};
  let rejectReady: (error: unknown) => void = () => {};
  const ready = new Promise<void>((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });
  let readySettled = false;
  const settleReady = (error?: unknown): void => {
    if (readySettled) return;
    readySettled = true;
    if (error === undefined) resolveReady();
    else rejectReady(error);
  };

  const handleLine = (line: string): void => {
    let message: {
      readonly op?: unknown;
      readonly id?: unknown;
      readonly text?: unknown;
      readonly message?: unknown;
    };
    try {
      message = JSON.parse(line) as typeof message;
    } catch {
      return;
    }
    if (message.op === "ready") {
      settleReady();
      return;
    }
    if (typeof message.id !== "string") return;
    const waiter = pending.get(message.id);
    if (waiter === undefined) return;
    pending.delete(message.id);
    if (message.op === "result" && typeof message.text === "string") {
      waiter.resolve(Object.freeze({ text: message.text }));
      return;
    }
    waiter.reject(new Error(
      typeof message.message === "string" ? message.message : "stt worker error",
    ));
  };

  const pumpStdout = async (): Promise<void> => {
    const reader = proc.stdout.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        stdoutBuffer += decoder.decode(value, { stream: true });
        let newline = stdoutBuffer.indexOf("\n");
        while (newline >= 0) {
          const line = stdoutBuffer.slice(0, newline).trim();
          stdoutBuffer = stdoutBuffer.slice(newline + 1);
          if (line.length > 0) handleLine(line);
          newline = stdoutBuffer.indexOf("\n");
        }
      }
    } finally {
      settleReady(new Error("stt worker closed before ready"));
      failPending(new Error("stt worker exited"));
    }
  };
  void pumpStdout();

  const readyTimer = setTimeout(() => {
    settleReady(new Error("stt worker ready timeout"));
    if (!disposed) void dispose();
  }, readyTimeoutMs);
  void ready.then(() => clearTimeout(readyTimer), () => clearTimeout(readyTimer));

  const killOnExit = (): void => {
    try { proc.kill("SIGKILL"); } catch { /* already gone */ }
  };
  process.once("exit", killOnExit);

  const writeLine = (payload: unknown): void => {
    if (disposed) throw new Error("stt worker disposed");
    proc.stdin.write(`${JSON.stringify(payload)}\n`);
    proc.stdin.flush();
  };

  let chain = Promise.resolve();

  const dispose = async (): Promise<void> => {
    if (disposed) {
      await proc.exited;
      return;
    }
    disposed = true;
    process.removeListener("exit", killOnExit);
    failPending(new Error("stt worker disposed"));
    try {
      proc.stdin.write(`${JSON.stringify({ op: "shutdown" })}\n`);
    } catch { /* stdin may already be closed */ }
    try {
      proc.stdin.end();
    } catch { /* already ended */ }
    const killer = setTimeout(() => {
      try { proc.kill("SIGKILL"); } catch { /* already gone */ }
    }, DISPOSE_KILL_MS);
    await proc.exited;
    clearTimeout(killer);
  };

  return Object.freeze({
    get pid(): number | null {
      return typeof proc.pid === "number" && proc.pid > 0 ? proc.pid : null;
    },
    waitUntilReady: () => ready,
    transcribe(request) {
      const run = chain.then(async () => {
        await ready;
        if (disposed) throw new Error("stt worker disposed");
        requestId += 1;
        const id = String(requestId);
        const result = new Promise<MlxWhisperTranscribeResult>((resolve, reject) => {
          pending.set(id, Object.freeze({ resolve, reject }));
        });
        writeLine({
          op: "transcribe",
          id,
          pcm_b64: Buffer.from(request.pcm).toString("base64"),
          sample_rate: request.sampleRate,
          channels: request.channels,
        });
        return await result;
      });
      chain = run.then(() => undefined, () => undefined);
      return run;
    },
    dispose,
  });
};

export const createMlxWhisperTranscriptionSource = (
  options: MlxWhisperTranscriptionSourceOptions,
): MlxWhisperTranscriptionSource => {
  const engine = options.engine
    ?? (options.subprocess === undefined
      ? null
      : createSubprocessMlxWhisperEngine(options.subprocess));
  if (engine === null) {
    throw new TypeError("mlx whisper source requires an engine or subprocess");
  }

  const windowSeconds = options.windowSeconds ?? DEFAULT_MLX_WHISPER_WINDOW_SECONDS;
  const minFlushSeconds = options.minFlushSeconds ?? DEFAULT_MLX_WHISPER_MIN_FLUSH_SECONDS;
  const silenceFlushSeconds = options.silenceFlushSeconds === undefined
    ? DEFAULT_MLX_WHISPER_SILENCE_SECONDS
    : options.silenceFlushSeconds;
  const idleFlushMs = options.idleFlushMs === undefined
    ? DEFAULT_MLX_WHISPER_IDLE_FLUSH_MS
    : options.idleFlushMs;
  if (!Number.isFinite(windowSeconds) || windowSeconds <= 0
    || !Number.isFinite(minFlushSeconds) || minFlushSeconds <= 0) {
    throw new TypeError("invalid mlx whisper window");
  }

  let disposed = false;

  return Object.freeze({
    engine,
    connect(input): TranscriptionConnection {
      if (!isPcm16Codec(input.codec)) {
        const error = new UnsupportedTranscriptionCodecError(input.codec);
        return Object.freeze({
          writeAudio(chunk: Uint8Array): void {
            if (chunk.byteLength === 0) return;
            input.onError(error);
          },
          finish(): void {},
        });
      }
      if (!Number.isInteger(input.channels) || input.channels !== 1) {
        const error = new UnsupportedTranscriptionFormatError(
          `unsupported transcription channels: ${String(input.channels)}`,
        );
        return Object.freeze({
          writeAudio(chunk: Uint8Array): void {
            if (chunk.byteLength === 0) return;
            input.onError(error);
          },
          finish(): void {},
        });
      }
      if (!Number.isFinite(input.sampleRate) || input.sampleRate <= 0) {
        const error = new UnsupportedTranscriptionFormatError("unsupported transcription sample rate");
        return Object.freeze({
          writeAudio(chunk: Uint8Array): void {
            if (chunk.byteLength === 0) return;
            input.onError(error);
          },
          finish(): void {},
        });
      }

      const frameBytes = BYTES_PER_PCM16_SAMPLE * input.channels;
      const windowBytes = Math.floor(input.sampleRate * windowSeconds) * frameBytes;
      const minFlushBytes = Math.floor(input.sampleRate * minFlushSeconds) * frameBytes;
      const silenceSamples = silenceFlushSeconds === null
        ? 0
        : Math.floor(input.sampleRate * silenceFlushSeconds);

      let accepting = true;
      let buffer = new Uint8Array(0);
      let sampleCursor = 0;
      let windowIndex = 0;
      let work = Promise.resolve();
      let idleTimer: ReturnType<typeof setTimeout> | null = null;

      const clearIdle = (): void => {
        if (idleTimer === null) return;
        clearTimeout(idleTimer);
        idleTimer = null;
      };

      const emitWindow = (pcm: Uint8Array): void => {
        const frames = Math.floor(pcm.byteLength / frameBytes);
        if (frames <= 0) return;
        const exact = pcm.byteLength === frames * frameBytes
          ? pcm
          : pcm.subarray(0, frames * frameBytes);
        const start = sampleCursor / input.sampleRate;
        sampleCursor += frames;
        const end = sampleCursor / input.sampleRate;
        const consumedSeconds = frames / input.sampleRate;
        windowIndex += 1;
        const id = `${input.sessionId}:mlx:${String(windowIndex).padStart(4, "0")}`;
        work = work.then(async () => {
          if (disposed) return;
          const result = await engine.transcribe({
            pcm: exact,
            sampleRate: input.sampleRate,
            channels: input.channels,
          });
          const text = result.text.trim();
          if (text.length === 0) return;
          const emission: TranscriptionEmission = Object.freeze({
            segment: Object.freeze({
              id,
              text,
              is_user: false,
              start,
              end,
            }),
            consumedSeconds,
          });
          input.onEmission(emission);
        }).catch(input.onError);
      };

      const flushReadyWindows = (forceRemainder: boolean): void => {
        while (buffer.byteLength >= windowBytes) {
          const window = buffer.subarray(0, windowBytes);
          buffer = buffer.subarray(windowBytes);
          emitWindow(window);
        }
        if (silenceFlushSeconds !== null && silenceSamples > 0
          && buffer.byteLength >= minFlushBytes
          && tailIsSilent(buffer, input.channels, silenceSamples)) {
          const remainder = buffer;
          buffer = new Uint8Array(0);
          emitWindow(remainder);
          return;
        }
        if (forceRemainder && buffer.byteLength >= frameBytes) {
          const remainder = buffer;
          buffer = new Uint8Array(0);
          emitWindow(remainder);
        }
      };

      const armIdle = (): void => {
        clearIdle();
        if (idleFlushMs === null || !accepting) return;
        idleTimer = setTimeout(() => {
          idleTimer = null;
          if (!accepting || disposed) return;
          if (buffer.byteLength >= minFlushBytes) flushReadyWindows(true);
        }, idleFlushMs);
      };

      return Object.freeze({
        writeAudio(chunk: Uint8Array): void {
          if (!accepting || disposed || chunk.byteLength === 0) return;
          buffer = concatBytes(buffer, chunk);
          flushReadyWindows(false);
          armIdle();
        },
        finish(): void {
          accepting = false;
          clearIdle();
          flushReadyWindows(true);
        },
      });
    },
    async dispose(): Promise<void> {
      if (disposed) return;
      disposed = true;
      await engine.dispose();
    },
  });
};
