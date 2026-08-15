// domain-pending(DIV-DOMCORE-012)

import { afterEach, describe, expect, test } from "bun:test";

import {
  MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE,
  MLX_WHISPER_VENV_ABSENT_MESSAGE,
  MLX_WHISPER_WORKER_STUB_PATH,
  STT_BOOTSTRAP_SCRIPT,
} from "./mlx-whisper-boot";
import {
  createMlxWhisperTranscriptionSource,
  createSubprocessMlxWhisperEngine,
  UnsupportedTranscriptionCodecError,
  UnsupportedTranscriptionFormatError,
  type MlxWhisperEngine,
  type MlxWhisperTranscribeRequest,
} from "./mlx-whisper-transcription-source";
import type { TranscriptionEmission } from "./transcription-source";

const SAMPLE_RATE = 16_000;
const PYTHON = "python3";

const pcm16 = (seconds: number, fill = 1_000): Uint8Array => {
  const samples = Math.floor(SAMPLE_RATE * seconds);
  const bytes = new Uint8Array(samples * 2);
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < samples; index += 1) view.setInt16(index * 2, fill, true);
  return bytes;
};

const waitUntil = async (predicate: () => boolean, timeoutMs = 1_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await Bun.sleep(5);
  }
  throw new Error("condition timeout");
};

const alive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

interface FakeEngine extends MlxWhisperEngine {
  readonly windows: Uint8Array[];
}

const fakeEngine = (
  texts: readonly string[] = [],
  transcribeImpl?: (request: MlxWhisperTranscribeRequest) => Promise<{ readonly text: string }>,
): FakeEngine => {
  const windows: Uint8Array[] = [];
  return {
    pid: null,
    windows,
    waitUntilReady: async () => {},
    async transcribe(request) {
      windows.push(request.pcm);
      if (transcribeImpl !== undefined) return await transcribeImpl(request);
      return { text: texts[windows.length - 1] ?? `window-${String(windows.length)}` };
    },
    async dispose() {},
  };
};

const connect = (engine: MlxWhisperEngine, overrides: {
  readonly codec?: string;
  readonly channels?: number;
  readonly sampleRate?: number;
  readonly windowSeconds?: number;
  readonly silenceFlushSeconds?: number | null;
  readonly idleFlushMs?: number | null;
} = {}) => {
  const emissions: TranscriptionEmission[] = [];
  const errors: unknown[] = [];
  const source = createMlxWhisperTranscriptionSource({
    engine,
    windowSeconds: overrides.windowSeconds ?? 3,
    silenceFlushSeconds: overrides.silenceFlushSeconds ?? null,
    idleFlushMs: overrides.idleFlushMs ?? null,
  });
  const connection = source.connect({
    sessionId: "session-1",
    sampleRate: overrides.sampleRate ?? SAMPLE_RATE,
    codec: overrides.codec ?? "pcm16",
    channels: overrides.channels ?? 1,
    onEmission: (emission) => emissions.push(emission),
    onError: (error) => errors.push(error),
  });
  return { source, connection, emissions, errors };
};

const subprocesses: Array<{ dispose: () => Promise<void> }> = [];

afterEach(async () => {
  for (const item of subprocesses.splice(0)) await item.dispose();
});

describe("createMlxWhisperTranscriptionSource windowing", () => {
  test("emits in order with consumedSeconds taken from PCM duration", async () => {
    const engine = fakeEngine(["first", "second", "tail"]);
    const { connection, emissions } = connect(engine);
    connection.writeAudio(pcm16(3));
    connection.writeAudio(pcm16(3));
    connection.writeAudio(pcm16(1.5));
    connection.finish();
    await waitUntil(() => emissions.length === 3);

    expect(engine.windows.map((window) => window.byteLength)).toEqual([
      SAMPLE_RATE * 3 * 2,
      SAMPLE_RATE * 3 * 2,
      SAMPLE_RATE * 1.5 * 2,
    ]);
    expect(emissions.map((emission) => emission.segment.text)).toEqual([
      "first",
      "second",
      "tail",
    ]);
    expect(emissions.map((emission) => emission.consumedSeconds)).toEqual([3, 3, 1.5]);
    expect(emissions.map((emission) => [emission.segment.start, emission.segment.end]))
      .toEqual([[0, 3], [3, 6], [6, 7.5]]);
    expect(emissions.map((emission) => emission.segment.id)).toEqual([
      "session-1:mlx:0001",
      "session-1:mlx:0002",
      "session-1:mlx:0003",
    ]);
  });

  test("writeAudio returns before the engine settles", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const engine = fakeEngine([], async () => {
      await gate;
      return { text: "later" };
    });
    const { connection, emissions } = connect(engine);
    connection.writeAudio(pcm16(3));
    expect(emissions).toEqual([]);
    release();
    await waitUntil(() => emissions.length === 1);
    expect(emissions[0]?.segment.text).toBe("later");
    expect(emissions[0]?.consumedSeconds).toBe(3);
  });

  test("rejects unimplemented codecs without feeding the engine", () => {
    const engine = fakeEngine();
    const { connection, errors } = connect(engine, { codec: "opus" });
    connection.writeAudio(pcm16(1));
    expect(errors[0]).toBeInstanceOf(UnsupportedTranscriptionCodecError);
    expect((errors[0] as UnsupportedTranscriptionCodecError).codec).toBe("opus");
    expect(engine.windows).toEqual([]);
  });

  test("rejects non-mono pcm16 without feeding the engine", () => {
    const engine = fakeEngine();
    const { connection, errors } = connect(engine, { channels: 2 });
    connection.writeAudio(pcm16(1));
    expect(errors[0]).toBeInstanceOf(UnsupportedTranscriptionFormatError);
    expect(engine.windows).toEqual([]);
  });

  test("linear16 is accepted as pcm16", async () => {
    const engine = fakeEngine(["ok"]);
    const { connection, emissions } = connect(engine, { codec: "linear16" });
    connection.writeAudio(pcm16(3));
    await waitUntil(() => emissions.length === 1);
    expect(emissions[0]?.segment.text).toBe("ok");
  });
});

describe("subprocess worker lifecycle", () => {
  test("dispose kills the worker", async () => {
    const engine = createSubprocessMlxWhisperEngine({
      pythonPath: PYTHON,
      workerPath: MLX_WHISPER_WORKER_STUB_PATH,
      model: "stub",
      readyTimeoutMs: 5_000,
    });
    subprocesses.push(engine);
    await engine.waitUntilReady();
    const pid = engine.pid;
    expect(pid).toBeGreaterThan(0);
    expect(alive(pid!)).toBe(true);
    await engine.dispose();
    await waitUntil(() => !alive(pid!), 2_000);
    expect(alive(pid!)).toBe(false);
  });

  test("the worker dies when the owner process exits without dispose", async () => {
    const owner = Bun.spawn([
      process.execPath,
      "-e",
      `
        import { createSubprocessMlxWhisperEngine } from ${JSON.stringify(new URL("./mlx-whisper-transcription-source.ts", import.meta.url).pathname)};
        import { MLX_WHISPER_WORKER_STUB_PATH } from ${JSON.stringify(new URL("./mlx-whisper-boot.ts", import.meta.url).pathname)};
        const engine = createSubprocessMlxWhisperEngine({
          pythonPath: "python3",
          workerPath: MLX_WHISPER_WORKER_STUB_PATH,
          model: "stub",
          readyTimeoutMs: 5000,
        });
        await engine.waitUntilReady();
        process.stdout.write(String(engine.pid));
        process.exit(0);
      `,
    ], {
      cwd: process.cwd(),
      stdout: "pipe",
      stderr: "pipe",
    });
    const pidText = await new Response(owner.stdout).text();
    const stderr = await new Response(owner.stderr).text();
    const exit = await owner.exited;
    expect(exit).toBe(0);
    expect(stderr).toBe("");
    const pid = Number(pidText);
    expect(pid).toBeGreaterThan(0);
    await waitUntil(() => !alive(pid), 2_000);
    expect(alive(pid)).toBe(false);
  });
});

test("dev-server refuses mlx-whisper when the venv is absent", async () => {
  const child = Bun.spawn([process.execPath, "apps/service/bin/dev-server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      OMI_STT_ENGINE: "mlx-whisper",
      OMI_STT_VENV: "/nonexistent-omi-stt-venv-proof",
      OMI_STT_MODEL: "",
    },
    stdout: "pipe",
    stderr: "pipe",
  });
  const stderr = await new Response(child.stderr).text();
  const stdout = await new Response(child.stdout).text();
  expect(await child.exited).toBe(1);
  expect(stderr).toContain(MLX_WHISPER_VENV_ABSENT_MESSAGE);
  expect(stderr).toContain(STT_BOOTSTRAP_SCRIPT);
  expect(stderr).not.toContain("/nonexistent-omi-stt-venv-proof");
  expect(stdout).not.toContain("/nonexistent-omi-stt-venv-proof");
});

test("dev-server refuses an unknown STT engine without printing it", async () => {
  const child = Bun.spawn([process.execPath, "apps/service/bin/dev-server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      OMI_STT_ENGINE: "cloud-stt-vendor",
      OMI_STT_VENV: "",
      OMI_STT_MODEL: "",
    },
    stdout: "pipe",
    stderr: "pipe",
  });
  const stderr = await new Response(child.stderr).text();
  expect(await child.exited).toBe(1);
  expect(stderr).toContain(MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE);
  expect(stderr).not.toContain("cloud-stt-vendor");
});
