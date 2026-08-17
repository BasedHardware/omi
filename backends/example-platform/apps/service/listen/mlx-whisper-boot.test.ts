// domain-pending(DIV-DOMCORE-012)

import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "bun:test";

import {
  DevSttConfigError,
  MLX_WHISPER_ENGINE,
  MLX_WHISPER_MODEL_ABSENT_MESSAGE,
  MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE,
  MLX_WHISPER_VENV_ABSENT_MESSAGE,
  STT_BOOTSTRAP_SCRIPT,
  STT_BOOTSTRAP_STAMP_SCHEMA,
  resolveDevSttConfig,
  serviceRepoRoot,
} from "./mlx-whisper-boot";

const directories: string[] = [];

afterEach(() => {
  for (const directory of directories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

const scratch = (): string => {
  const directory = mkdtempSync(join(tmpdir(), "omi-stt-boot-"));
  directories.push(directory);
  return directory;
};

const plantVenv = (root: string, model = "mlx-community/whisper-large-v3-turbo"): string => {
  const venv = join(root, ".local", "stt", "venv");
  mkdirSync(join(venv, "bin"), { recursive: true });
  mkdirSync(join(venv, "lib", "python3.12", "site-packages", "mlx_whisper"), { recursive: true });
  mkdirSync(join(root, ".local", "stt", "hf-cache", "hub", `models--${model.replaceAll("/", "--")}`), {
    recursive: true,
  });
  writeFileSync(join(venv, "bin", "python"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
  writeFileSync(join(venv, "lib", "python3.12", "site-packages", "mlx_whisper", "__init__.py"), "");
  writeFileSync(join(root, ".local", "stt", "bootstrap.json"), `${JSON.stringify({
    schema: STT_BOOTSTRAP_STAMP_SCHEMA,
    engine: MLX_WHISPER_ENGINE,
    model,
    python: "3.12.0",
  })}\n`);
  return venv;
};

describe("resolveDevSttConfig", () => {
  test("unset engine keeps the scripted source", () => {
    expect(resolveDevSttConfig({}, { repoRoot: scratch() })).toEqual({ kind: "scripted" });
    expect(resolveDevSttConfig({ OMI_STT_ENGINE: "  " }, { repoRoot: scratch() }))
      .toEqual({ kind: "scripted" });
  });

  test("unknown engine fails closed without interpolating the value", () => {
    expect(() => resolveDevSttConfig({ OMI_STT_ENGINE: "deepgram" }, { repoRoot: scratch() }))
      .toThrow(DevSttConfigError);
    try {
      resolveDevSttConfig({ OMI_STT_ENGINE: "deepgram" }, { repoRoot: scratch() });
    } catch (error) {
      expect(error).toBeInstanceOf(DevSttConfigError);
      expect((error as Error).message).toBe(MLX_WHISPER_UNKNOWN_ENGINE_MESSAGE);
      expect((error as Error).message).not.toContain("deepgram");
    }
  });

  test("mlx-whisper without a venv points at the bootstrap script", () => {
    const root = scratch();
    expect(() => resolveDevSttConfig({ OMI_STT_ENGINE: "mlx-whisper" }, { repoRoot: root }))
      .toThrow(MLX_WHISPER_VENV_ABSENT_MESSAGE);
    expect(MLX_WHISPER_VENV_ABSENT_MESSAGE).toContain(STT_BOOTSTRAP_SCRIPT);
  });

  test("mlx-whisper without a model stamp fails closed", () => {
    const root = scratch();
    plantVenv(root);
    rmSync(join(root, ".local", "stt", "bootstrap.json"));
    rmSync(join(root, ".local", "stt", "hf-cache"), { recursive: true, force: true });
    expect(() => resolveDevSttConfig({ OMI_STT_ENGINE: "mlx-whisper" }, { repoRoot: root }))
      .toThrow(MLX_WHISPER_MODEL_ABSENT_MESSAGE);
  });

  test("mlx-whisper with a planted venv and stamp resolves paths", () => {
    const root = scratch();
    const venv = plantVenv(root);
    const config = resolveDevSttConfig({ OMI_STT_ENGINE: "mlx-whisper" }, { repoRoot: root });
    expect(config.kind).toBe("mlx-whisper");
    if (config.kind !== "mlx-whisper") return;
    expect(config.pythonPath).toBe(join(venv, "bin", "python"));
    expect(config.venvPath).toBe(venv);
    expect(config.model).toBe("mlx-community/whisper-large-v3-turbo");
    expect(config.workerPath).toContain("mlx-whisper-worker.py");
  });
});

test("production entrypoints and app-facing do not import the mlx whisper source", () => {
  const root = serviceRepoRoot();
  const files = [
    "apps/service/app-facing.ts",
    "drivers/postgres/firebase-authorized-memory-service-process.ts",
    "drivers/postgres/firebase-authorized-memory-service-app.ts",
    "apps/mcp/bun-http.ts",
  ];
  for (const relative of files) {
    const text = readFileSync(join(root, relative), "utf8");
    expect(text).not.toContain("mlx-whisper");
    expect(text).not.toContain("createMlxWhisperTranscriptionSource");
    expect(text).not.toContain(".local/stt");
  }
  const devServer = readFileSync(join(root, "apps/service/bin/dev-server.ts"), "utf8");
  expect(devServer).toContain("createMlxWhisperTranscriptionSource");
  expect(devServer).toContain("OMI_STT_ENGINE");
});
