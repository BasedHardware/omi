import { describe, expect, test } from "bun:test";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  appendRuntimeLog,
  createRuntimeLogSink,
  normalizeRuntimeLogRecord,
  resolveRuntimeLogDirectory,
  runtimeLogPath,
  sanitizeRuntimeLogText,
} from "./runtime-log";

const scratch = (): string => mkdtempSync(join(tmpdir(), "omi-runtime-log-"));

const readLines = (path: string): readonly Record<string, unknown>[] => {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
};

describe("runtime JSONL log", () => {
  test("resolves the coordinator log directory from OMI_DEV_STACK_RUNDIR", () => {
    expect(resolveRuntimeLogDirectory("/tmp/custom-logs")).toBe("/tmp/custom-logs");
    const previous = process.env.OMI_DEV_STACK_RUNDIR;
    process.env.OMI_DEV_STACK_RUNDIR = "/tmp/omi-run-dir-proof";
    try {
      expect(resolveRuntimeLogDirectory()).toBe("/tmp/omi-run-dir-proof/logs");
      expect(runtimeLogPath("service")).toBe("/tmp/omi-run-dir-proof/logs/service.jsonl");
    } finally {
      if (previous === undefined) delete process.env.OMI_DEV_STACK_RUNDIR;
      else process.env.OMI_DEV_STACK_RUNDIR = previous;
    }
  });

  test("writes one JSON object per line with the required envelope", () => {
    const dir = scratch();
    try {
      const sink = createRuntimeLogSink({
        proc: "service",
        dir,
        nowIso: () => "2026-08-15T00:00:00.000Z",
      });
      sink.write({
        proc: "service",
        level: "info",
        event: "service.boot",
        persona: "qa",
        stt_engine: "scripted",
        gateway_kind: "none",
      });
      const [record] = readLines(join(dir, "service.jsonl"));
      expect(record).toEqual({
        ts: "2026-08-15T00:00:00.000Z",
        proc: "service",
        level: "info",
        event: "service.boot",
        persona: "qa",
        stt_engine: "scripted",
        gateway_kind: "none",
      });
      expect(readFileSync(join(dir, "service.jsonl"), "utf8").endsWith("\n")).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("strips secrets and never persists a bearer token or origin", () => {
    const dir = scratch();
    const token = "secret-bearer-token-xyz-do-not-log";
    try {
      const sink = createRuntimeLogSink({
        proc: "service",
        dir,
        nowIso: () => "2026-08-15T00:00:00.000Z",
      });
      sink.write({
        proc: "service",
        level: "info",
        event: "service.request",
        authorization: `Bearer ${token}`,
        token,
        api_key: "sk-live-secret",
        body: "chat message body",
        detail: `Authorization: Bearer ${token} http://127.0.0.1:4851/v1/memories`,
      });
      const file = readFileSync(join(dir, "service.jsonl"), "utf8");
      expect(file).not.toContain(token);
      expect(file).not.toContain("sk-live-secret");
      expect(file).not.toContain("chat message body");
      expect(file).not.toContain("http://127.0.0.1");
      const [record] = readLines(join(dir, "service.jsonl"));
      expect(record).not.toHaveProperty("authorization");
      expect(record).not.toHaveProperty("token");
      expect(record).not.toHaveProperty("api_key");
      expect(record).not.toHaveProperty("body");
      expect(record.detail).toBe("Authorization: Bearer [redacted] [redacted-origin]");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("rotation keeps the current file and one previous generation under the cap", () => {
    const dir = scratch();
    try {
      const sink = createRuntimeLogSink({
        proc: "service",
        dir,
        maxBytes: 200,
        nowIso: () => "2026-08-15T00:00:00.000Z",
      });
      for (const index of [1, 2, 3, 4, 5, 6]) {
        sink.write({
          proc: "service",
          level: "info",
          event: "service.request",
          path: `/v1/memories/${index}`,
          marker: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        });
      }
      const current = join(dir, "service.jsonl");
      const previous = `${current}.1`;
      expect(existsSync(current)).toBe(true);
      expect(existsSync(previous)).toBe(true);
      expect(readFileSync(current).length).toBeLessThanOrEqual(200);
      expect(readFileSync(previous).length).toBeLessThanOrEqual(200);
      expect(readLines(current).length).toBeGreaterThan(0);
      expect(readLines(previous).length).toBeGreaterThan(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("a path that cannot be created degrades to the fallback and does not throw", () => {
    const dir = scratch();
    const blocked = join(dir, "not-a-directory");
    writeFileSync(blocked, "file\n");
    const fallback: string[] = [];
    try {
      const sink = createRuntimeLogSink({
        proc: "service",
        dir: blocked,
        onFallback: (line, reason) => {
          fallback.push(`${reason}:${line}`);
        },
      });
      expect(() => {
        sink.write({ proc: "service", level: "info", event: "service.boot" });
      }).not.toThrow();
      expect(fallback.length).toBeGreaterThan(0);
      expect(existsSync(join(blocked, "service.jsonl"))).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("normalize rejects unknown procs and malformed event slugs", () => {
    const nowIso = () => "2026-08-15T00:00:00.000Z";
    expect(normalizeRuntimeLogRecord({
      proc: "service",
      level: "info",
      event: "Not A Slug",
    }, nowIso)).toBeNull();
    expect(normalizeRuntimeLogRecord({
      proc: "service",
      level: "info",
      event: "service.request",
    }, nowIso)?.event).toBe("service.request");
    expect(sanitizeRuntimeLogText("token=abc123")).toContain("[redacted]");
  });

  test("appendRuntimeLog writes through the shared sink", () => {
    const dir = scratch();
    try {
      appendRuntimeLog({
        proc: "service",
        level: "warn",
        event: "dev-stack.refused",
        dir,
        ts: "2026-08-15T00:00:01.000Z",
        reason: "port_occupied",
      });
      expect(readLines(join(dir, "service.jsonl"))).toEqual([{
        ts: "2026-08-15T00:00:01.000Z",
        proc: "service",
        level: "warn",
        event: "dev-stack.refused",
        reason: "port_occupied",
      }]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("the CLI append entry used by the dev stack writes a JSONL line", () => {
    const dir = scratch();
    try {
      const result = Bun.spawnSync([
        process.execPath,
        "apps/service/observability/runtime-log.ts",
        "--append",
        "--proc", "service",
        "--level", "info",
        "--event", "dev-stack.start",
        "--dir", dir,
        "--field", "run_id=run-cli-proof",
      ], { cwd: join(import.meta.dir, "../../..") });
      expect(result.exitCode).toBe(0);
      expect(readLines(join(dir, "service.jsonl"))[0]).toMatchObject({
        proc: "service",
        level: "info",
        event: "dev-stack.start",
        run_id: "run-cli-proof",
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
